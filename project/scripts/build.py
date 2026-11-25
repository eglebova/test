#!/usr/bin/env python3
"""Build and validate the no-backend static website using only Python stdlib."""
from __future__ import annotations
import argparse
from datetime import date
from html.parser import HTMLParser
from html import escape, unescape
from pathlib import Path
from urllib.parse import urlsplit
import re
import posixpath
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ITEMS = [
    "index.html", "404.html", "favicon.svg", "robots.txt", ".htaccess",
    "assets", "about", "practice", "working-process", "remuneration", "documents", "contacts", "articles",
]
FORBIDDEN = [
    "адрес офиса", "адрес адвокатского кабинета", "пресненский",
    "записаться на приём", "записаться в офис", "личный приём",
    "карта проезда", "схема проезда", "координаты", "postaladdress", "streetaddress",
    "58 918", "58918", "3 000+", "3000+", "92%",
    "гарантируем результат", "гарантия выигрыша", "выиграем дело", "100% выигрыш",
    "лучший адвокат", "номер один", "отзывы доверителей", "рейтинг адвоката",
    "уголовные дела", "защита по уголовным делам", "юридическая компания", "юридическая фирма",
    "публичная оферта", "акцепт оферты", "загрузить документы", "прикрепить файл",
    "бесплатная консультация", "первая консультация бесплатно", "получить бесплатную консультацию",
    "бесплатный анализ документов", "бесплатная юридическая консультация",
]

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.title = False
        self.has_title = False
        self.h1_count = 0
        self.has_description = False
        self.has_viewport = False
        self.has_lang = False
        self.form_count = 0
        self.iframe_count = 0
        self.script_count = 0
        self.external_assets: list[str] = []
        self.img_without_alt = 0
        self.inline_handlers: list[str] = []
        self.refresh_meta = 0
        self.embedded_content = 0
        self.unsafe_new_tabs = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for name in a:
            if name and name.lower().startswith("on"):
                self.inline_handlers.append(name)
        if tag == "html" and a.get("lang") == "ru":
            self.has_lang = True
        if tag == "title":
            self._in_title = True
        if tag == "h1":
            self.h1_count += 1
        if tag == "meta":
            if a.get("name", "").lower() == "description" and a.get("content"):
                self.has_description = True
            if a.get("name", "").lower() == "viewport" and a.get("content"):
                self.has_viewport = True
            if a.get("http-equiv", "").lower() == "refresh":
                self.refresh_meta += 1
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
            if a.get("target", "").lower() == "_blank" and not {x.lower() for x in a.get("rel", "").split()} & {"noopener", "noreferrer"}:
                self.unsafe_new_tabs += 1
        if tag in ("img", "script") or (tag == "link" and a.get("rel", "").lower() in ("stylesheet", "icon", "preload", "modulepreload")):
            attr = "src" if tag in ("img", "script") else "href"
            val = a.get(attr, "")
            if val.startswith(("http://", "https://", "//")):
                self.external_assets.append(val)
        if tag == "img" and "alt" not in a:
            self.img_without_alt += 1
        if tag == "form":
            self.form_count += 1
        if tag == "iframe":
            self.iframe_count += 1
        if tag in ("object", "embed", "audio", "video"):
            self.embedded_content += 1
        if tag == "script":
            self.script_count += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
            self.has_title = True


def polish_editorial_copy(raw: str, page: Path) -> str:
    """Replace first-person promotional wording with neutral professional language."""
    replacements = [
        ("Я представляю доверителей в судах и помогаю гражданам и организациям решать сложные правовые вопросы.",
         "Представительство доверителей в судах и правовая помощь гражданам и организациям по сложным правовым вопросам."),
        ("Я — Елена Алексеевна Глебова, адвокат", "Адвокат Елена Алексеевна Глебова"),
        ("Я, адвокат Глебова Елена Алексеевна, оказываю правовую помощь",
         "Адвокат Глебова Елена Алексеевна оказывает правовую помощь"),
        ("Я отдельно согласую безопасный способ передачи материалов.",
         "Безопасный способ передачи материалов согласуется отдельно."),
        ("Я прошу не направлять мне в первом сообщении подробности дела и документы.",
         "В первом сообщении не следует направлять подробности дела и документы."),
        ("Я предлагаю сначала обозначить общую категорию правового вопроса",
         "Для начала достаточно обозначить общую категорию правового вопроса"),
        ("Позвонить мне", "Позвонить"),
        ("Написать мне", "Написать"),
        ("Связаться со мной", "Контакты"),
        ("Обсудить со мной правовой вопрос", "Обсудить правовой вопрос"),
        ("Моя практика", "Направления помощи"),
        ("Мои материалы", "Публикации"),
        ("Мои контакты", "Контакты"),
        ("Как я работаю", "Порядок работы"),
        ("Все мои правовые материалы", "Все правовые материалы"),
        ("Посмотреть ориентиры моего вознаграждения", "Ориентиры вознаграждения"),
    ]
    for old, new in replacements:
        raw = raw.replace(old, new)
    return raw


def collect_html_files(folder: Path) -> list[Path]:
    return sorted(folder.rglob("*.html"))


def url_for_page(dist: Path, page: Path) -> str:
    rel = page.relative_to(dist).as_posix()
    if rel == "index.html":
        return "/"
    if rel.endswith("/index.html"):
        return "/" + rel[:-len("index.html")]
    return "/" + rel


def relative_site_url(value: str, page: Path, dist: Path) -> str:
    """Rewrite site-root URLs as page-relative URLs so the site also works via file://."""
    if not value.startswith("/") or value.startswith("//"):
        return value
    from urllib.parse import urlunsplit
    parsed = urlsplit(value)
    page_parent = page.parent.relative_to(dist).as_posix()
    target = parsed.path.lstrip("/") or "."
    rel = posixpath.relpath(target, start=page_parent)
    if rel == ".":
        rel = "./"
    elif parsed.path.endswith("/") and not rel.endswith("/"):
        rel += "/"
    return urlunsplit(("", "", rel, parsed.query, parsed.fragment))


def localize_html_urls(raw: str, page: Path, dist: Path) -> str:
    attr = re.compile(r'(?P<prefix>\b(?:href|src|poster)\s*=\s*)(?P<q>["\'])(?P<url>[^"\']*)(?P=q)', re.I)
    return attr.sub(lambda m: m.group("prefix") + m.group("q") + relative_site_url(m.group("url"), page, dist) + m.group("q"), raw)


def enhance_article(raw: str, page: Path, dist: Path) -> str:
    """Add a navigable contents list and a factual author note to long article pages."""
    if page.parent.parent.name != "articles" or page.parent.name == "articles":
        return raw
    match = re.search(r'(<article class="article-content">)(.*?)(</article>)', raw, re.S)
    if not match:
        return raw
    raw = raw.replace(
        '<article class="article-content">',
        '<article class="article-content" itemscope itemtype="https://schema.org/Article">',
        1
    )
    match = re.search(r'(<article class="article-content"[^>]*>)(.*?)(</article>)', raw, re.S)
    if not match:
        return raw
    body = match.group(2)
    h1 = re.search(r'<h1[^>]*>(.*?)</h1>', raw, re.S)
    if h1:
        headline = unescape(re.sub(r"<[^>]+>", "", h1.group(1))).strip()
        body = '<meta itemprop="headline" content="' + escape(headline, quote=True) + '">' + body
    heading_pattern = re.compile(r'<h2\b([^>]*)>(.*?)</h2>', re.S)
    headings = list(heading_pattern.finditer(body))
    if len(headings) >= 5 and 'class="article-toc"' not in body:
        replacements = []
        links = []
        for index, heading in enumerate(headings, 1):
            attrs, inner = heading.group(1), heading.group(2)
            existing = re.search(r"\bid=['\"]([^'\"]+)['\"]", attrs)
            anchor_id = existing.group(1) if existing else f"article-section-{index}"
            label = unescape(re.sub(r"<[^>]+>", "", inner)).strip()
            if not existing:
                replacement = f'<h2{attrs} id="{anchor_id}">{inner}</h2>'
                replacements.append((heading.start(), heading.end(), replacement))
            links.append(f'<li><a href="#{escape(anchor_id, quote=True)}">{escape(label)}</a></li>')
        for start, end, replacement in reversed(replacements):
            body = body[:start] + replacement + body[end:]
        toc = '<nav class="article-toc" aria-label="Содержание статьи"><strong>Содержание</strong><ol>' + "".join(links) + '</ol></nav>'
        meta = re.search(r'(<p class="article-meta">.*?</p>)', body, re.S)
        if meta:
            body = body[:meta.end()] + toc + body[meta.end():]
        else:
            body = toc + body
    if 'class="article-author"' not in body:
        about_url = relative_site_url("/about/", page, dist)
        author = (
            '<aside class="article-author" itemprop="author" itemscope itemtype="https://schema.org/Person"><p><strong>Автор материала</strong><br>'
            '<span itemprop="name">Елена Алексеевна Глебова</span>, <span itemprop="jobTitle">адвокат</span> Адвокатской палаты Московской области.</p>'
            f'<a href="{escape(about_url, quote=True)}">Сведения об адвокате</a></aside>'
        )
        body += author
    return raw[:match.start(2)] + body + raw[match.end(2):]


def add_person_and_service_schema(raw: str, page: Path, dist: Path) -> str:
    """Add Schema.org microdata only where the page content supports it."""
    rel = page.relative_to(dist).as_posix()
    if rel == "index.html":
        raw = raw.replace(
            '<main id="main">',
            '<main id="main" itemscope itemtype="https://schema.org/LegalService">'
            '<meta itemprop="name" content="Адвокатская практика Глебовой Елены Алексеевны">'
            '<meta itemprop="telephone" content="+79104707654">'
            '<meta itemprop="email" content="e_glebova@mail.ru">'
            '<meta itemprop="areaServed" content="Россия">',
            1
        )
        raw = raw.replace(
            'Я — Елена Алексеевна Глебова, адвокат',
            '<span itemprop="provider" itemscope itemtype="https://schema.org/Person"><span itemprop="name">Елена Алексеевна Глебова</span><meta itemprop="jobTitle" content="Адвокат"></span> — адвокат',
            1
        )
    elif rel == "about/index.html":
        raw = raw.replace(
            '<main id="main">',
            '<main id="main" itemscope itemtype="https://schema.org/Person">'
            '<meta itemprop="jobTitle" content="Адвокат">'
            '<meta itemprop="telephone" content="+79104707654">'
            '<meta itemprop="email" content="e_glebova@mail.ru">'
            '<span itemprop="memberOf" itemscope itemtype="https://schema.org/Organization"><meta itemprop="name" content="Адвокатская палата Московской области"></span>',
            1
        )
        raw = raw.replace('<h1>Елена Алексеевна Глебова</h1>', '<h1 itemprop="name">Елена Алексеевна Глебова</h1>', 1)
        raw = re.sub(r'(<img class="about-photo"[^>]*)(>)', r'\1 itemprop="image"\2', raw, count=1)
        raw = raw.replace('<p class="lead">Меня зовут', '<p class="lead" itemprop="description">Меня зовут', 1)
    return raw


def resolve_local(path: str, dist: Path, page: Path) -> bool:
    if not path or path == "#":
        return True
    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc:
        return True
    if not parsed.path:
        return True
    candidate_path = parsed.path
    candidate = (page.parent / candidate_path).resolve()
    try:
        candidate.relative_to(dist)
    except ValueError:
        return False
    candidates = [candidate, candidate / "index.html"]
    return any(p.is_file() for p in candidates)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build static site and run content/link QA")
    ap.add_argument("--origin", required=True, help="Canonical HTTPS origin, e.g. https://example.ru")
    ap.add_argument("--out", default=str(ROOT / "dist"), help="Output directory (default: ./dist)")
    args = ap.parse_args()
    origin = args.origin.rstrip("/")
    parsed_origin = urlsplit(origin)
    if parsed_origin.scheme != "https" or not parsed_origin.netloc or parsed_origin.path:
        print("FAIL: --origin must be an HTTPS origin without path, e.g. https://example.ru", file=sys.stderr)
        return 2
    if any(ch in origin for ch in " <>\"'`"):
        print("FAIL: invalid characters in --origin", file=sys.stderr)
        return 2

    is_test_origin = parsed_origin.hostname in {"localhost", "127.0.0.1", "qa.invalid", "example.invalid"} or (parsed_origin.hostname or "").endswith(".invalid")

    requested_dist = Path(args.out).resolve()
    # Never allow the output path to replace the project or overlap a source
    # directory. All work is staged beside the destination and published only
    # after every validation succeeds; a failed build preserves the last good release.
    if requested_dist == ROOT or requested_dist in ROOT.parents:
        print("FAIL: output directory cannot be the project root or one of its parents", file=sys.stderr)
        return 2
    protected_sources = [(ROOT / item).resolve() for item in PUBLIC_ITEMS]
    for source in protected_sources:
        if requested_dist == source or requested_dist in source.parents or source in requested_dist.parents:
            print(f"FAIL: output directory overlaps a public source path: {source.relative_to(ROOT) if source.is_relative_to(ROOT) else source}", file=sys.stderr)
            return 2
    if requested_dist.exists() and not requested_dist.is_dir():
        print("FAIL: output path exists and is not a directory", file=sys.stderr)
        return 2
    requested_dist.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=requested_dist.name + ".staging-", dir=str(requested_dist.parent)))
    dist = stage

    for item in PUBLIC_ITEMS:
        src = ROOT / item
        if not src.exists():
            print(f"FAIL: missing required public item: {item}", file=sys.stderr)
            return 2
        dst = dist / item
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)

    html_files = collect_html_files(dist)
    errors: list[str] = []
    checked_links = 0
    for page in html_files:
        raw = page.read_text(encoding="utf-8")
        raw = polish_editorial_copy(raw, page)
        public_path = url_for_page(dist, page)
        canonical = origin + public_path
        marker = '  <!-- canonical and og:url are injected by scripts/build.py after the domain is selected -->'
        if page.name != "404.html":
            inject = f'<link rel="canonical" href="{canonical}">\n  <meta property="og:url" content="{canonical}">'
            raw = raw.replace(marker, "  " + inject)
        else:
            raw = raw.replace(marker, "")
        raw = raw.replace("__CANONICAL_URL__", canonical)
        raw = add_person_and_service_schema(raw, page, dist)
        raw = enhance_article(raw, page, dist)
        raw = localize_html_urls(raw, page, dist)
        # The distinction between the free organisational call and paid legal advice is visible site-wide.
        if "</footer>" in raw and "footer-brief-note" not in raw:
            footer_note = (
                '<div class="container footer-brief-note"><p><strong>Ознакомительная консультация по телефону — бесплатно.</strong> '
                'Это краткое организационное обсуждение общей категории обращения, возможного объёма правовой помощи, стоимости и записи; '
                'без изучения документов и рекомендаций по существу. '
                '<strong>Развёрнутая консультация (до 1 часа) — 3 500 ₽.</strong></p></div>'
            )
            raw = raw.replace("</footer>", footer_note + "</footer>", 1)
        # Native disclosure navigation keeps the mobile header compact without JavaScript.
        nav_pattern = re.compile(r'<nav class="primary-nav" aria-label="Основная навигация">.*?</nav>', re.S)
        raw = nav_pattern.sub(lambda match: '<details class="mobile-nav"><summary>Меню</summary>' + match.group(0) + '</details>', raw, count=1)
        if "consumer-penalty-damages-2021-2026" in page.as_posix():
            raw = re.sub(r'<meta name="robots" content="[^"]*">', '<meta name="robots" content="noindex,follow">', raw, count=1, flags=re.I)
        # Test builds must not be indexable even if a page template says index,follow.
        if is_test_origin or page.name == "404.html":
            raw = re.sub(r'<meta name="robots" content="[^"]*">', '<meta name="robots" content="noindex,nofollow">', raw, count=1, flags=re.I)
        else:
            raw = re.sub(r'<meta name="robots" content="noindex,nofollow">', '<meta name="robots" content="index,follow">', raw, count=1, flags=re.I)
        page.write_text(raw, encoding="utf-8")

        parser = PageParser()
        parser.feed(raw)
        rel = page.relative_to(dist).as_posix()
        if not parser.has_lang:
            errors.append(f"{rel}: html lang=ru is missing")
        if not parser.has_title:
            errors.append(f"{rel}: title is missing")
        if not parser.has_description:
            errors.append(f"{rel}: meta description is missing")
        if not parser.has_viewport:
            errors.append(f"{rel}: viewport meta is missing")
        if parser.h1_count != 1:
            errors.append(f"{rel}: expected exactly one h1, found {parser.h1_count}")
        if rel == "remuneration/index.html":
            if "Ознакомительная консультация по телефону" not in raw or "бесплатно" not in raw:
                errors.append(f"{rel}: free introductory phone consultation wording is missing")
            if "Развёрнутая консультация (до 1 часа)" not in raw or "3 500 ₽" not in raw:
                errors.append(f"{rel}: paid consultation wording or fee is missing")
            if re.search(r"(?<![А-Яа-яЁё])Я(?=[\\s,.:—])", raw):
                errors.append(f"{rel}: first-person pronoun remains in the fee page")
        if parser.form_count:
            errors.append(f"{rel}: HTML forms are disabled in this release")
        if parser.iframe_count:
            errors.append(f"{rel}: iframe is not allowed")
        if parser.script_count:
            errors.append(f"{rel}: JavaScript is disabled in this release")
        if parser.inline_handlers:
            errors.append(f"{rel}: inline event handler found: {parser.inline_handlers[0]}")
        if parser.refresh_meta:
            errors.append(f"{rel}: meta refresh redirect is not allowed")
        if parser.embedded_content:
            errors.append(f"{rel}: embedded active/media content is not allowed in release 1")
        if parser.unsafe_new_tabs:
            errors.append(f"{rel}: target=_blank link needs rel=noopener or noreferrer")
        if parser.external_assets:
            errors.append(f"{rel}: external asset request found: {parser.external_assets[0]}")
        if parser.img_without_alt:
            errors.append(f"{rel}: image without alt attribute")
        for href in parser.links:
            checked_links += 1
            parsed = urlsplit(href)
            if parsed.scheme in ("mailto", "tel", "https", "http") or parsed.netloc or href.startswith("#"):
                continue
            if not resolve_local(href, dist, page):
                errors.append(f"{rel}: unresolved local link {href}")

    # Content restrictions are checked against the complete public build, including metadata.
    for file in dist.rglob("*"):
        if not file.is_file():
            continue
        try:
            text = file.read_text(encoding="utf-8").lower()
        except UnicodeDecodeError:
            continue
        for pattern in FORBIDDEN:
            if pattern.lower() in text:
                errors.append(f"{file.relative_to(dist).as_posix()}: forbidden content pattern: {pattern}")
        if "__canonical_url__" in text or "__site_origin__" in text:
            errors.append(f"{file.relative_to(dist).as_posix()}: unresolved template token")

    # Do not invite indexing of reserved/test origins used for local QA.
    if is_test_origin:
        robots_text = "User-agent: *\nDisallow: /\n"
    else:
        robots_text = "User-agent: *\nAllow: /\nDisallow: /.git/\nDisallow: /.env\nSitemap: " + origin + "/sitemap.xml\n"
    (dist / "robots.txt").write_text(robots_text, encoding="utf-8")
    urls = []
    for page in html_files:
        if page.name == "404.html":
            continue
        page_text = page.read_text(encoding="utf-8").lower()
        if 'name="robots" content="noindex' in page_text:
            continue
        path = url_for_page(dist, page)
        urls.append(origin + path)
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc in urls:
        sitemap.append(f'  <url><loc>{loc}</loc></url>')
    sitemap.append('</urlset>')
    (dist / "sitemap.xml").write_text("\n".join(sitemap) + "\n", encoding="utf-8")

    # Check deployment artifacts and ensure only whitelisted public material is emitted.
    actual = sorted(p.relative_to(dist).as_posix() for p in dist.rglob("*") if p.is_file())
    if any(p.startswith(("scripts/", "deploy/", "project-notes/", "config/")) for p in actual):
        errors.append("private development material leaked into dist")
    if errors:
        print(f"FAIL: {len(errors)} issue(s)")
        for e in errors:
            print(" -", e)
        shutil.rmtree(stage, ignore_errors=True)
        return 1
    backup = requested_dist.with_name(requested_dist.name + ".previous")
    if backup.exists():
        if backup.is_dir():
            shutil.rmtree(backup)
        else:
            backup.unlink()
    if requested_dist.exists():
        requested_dist.replace(backup)
    stage.replace(requested_dist)
    if backup.exists():
        if backup.is_dir():
            shutil.rmtree(backup)
        else:
            backup.unlink()
    print("PASS: static build created and atomically published")
    print(f"Pages: {len(html_files)} | Internal links checked: {checked_links} | Canonical origin: {origin}")
    print("Static release: no server-side form processing, uploads, analytics, cookies, external assets or contact form.")
    print(f"Output: {requested_dist}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
