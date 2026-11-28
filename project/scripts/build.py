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
    "index.html", "404.html", "favicon.svg", "robots.txt",
    "assets", "about", "practice", "working-process", "remuneration", "documents", "contacts", "articles", "privacy-policy",
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
    "ознакомительная консультация по телефону",
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


def _mask_editorial_blocks(raw: str, page: Path) -> tuple[str, list[str]]:
    """Temporarily protect legal examples, answers and long-form article bodies."""
    ranges: list[tuple[int, int]] = []

    def find_ranges(tag: str, class_name: str) -> None:
        opener = re.compile(
            rf'<{tag}\b[^>]*\bclass=["\'][^"\']*\b{re.escape(class_name)}\b[^"\']*["\'][^>]*>',
            re.I,
        )
        token = re.compile(rf'</?{tag}\b[^>]*>', re.I)
        for opening in opener.finditer(raw):
            depth = 0
            for match in token.finditer(raw, opening.start()):
                value = match.group(0)
                if value.lower().startswith(f'</{tag}'):
                    depth -= 1
                elif not value.rstrip().endswith('/>'):
                    depth += 1
                if depth == 0:
                    ranges.append((opening.start(), match.end()))
                    break

    find_ranges("details", "consultation-disclosure")
    find_ranges("div", "consultation-modal")
    if page.parent.parent.name == "articles" and page.parent.name != "articles":
        find_ranges("article", "article-content")

    # Merge overlapping ranges so nested protected blocks are restored only once.
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    protected: list[str] = []
    for index, (start, end) in reversed(list(enumerate(merged))):
        marker = f"__LEGAL_CONTENT_PRESERVED_{index}__"
        protected.append((marker, raw[start:end]))
        raw = raw[:start] + marker + raw[end:]
    protected.reverse()
    return raw, protected


def polish_editorial_copy(raw: str, page: Path) -> str:
    """Keep the attorney's first-person voice while removing the explicit 'I' pronoun."""
    raw, protected = _mask_editorial_blocks(raw, page)

    # Remove the narrow information strip and the redundant subtitle under the name.
    raw = re.sub(
        r'<div class="topline">\s*<div class="container topline-inner">[\s\S]*?</div>\s*</div>\s*',
        '',
        raw,
        flags=re.I,
    )
    header_start = raw.find("<header")
    header_end = raw.find("</header>", header_start)
    if header_start >= 0 and header_end > header_start:
        header = raw[header_start:header_end]
        header = re.sub(
            r'(<span class="brand-text"><strong>[^<]*</strong>)\s*<small>[^<]*</small>',
            r'\1',
            header,
            count=1,
        )
        header = re.sub(
            r'<a class="nav-link" href="[^"]+"(?: aria-current="page")?>Главная</a>',
            '',
            header,
            count=1,
        )
        raw = raw[:header_start] + header + raw[header_end:]

    replacements = [
        ("Я, адвокат Глебова Елена Алексеевна, оказываю правовую помощь гражданам и организациям, представляю доверителей в судах и анализирую сложные правовые вопросы.",
         "Оказываю правовую помощь гражданам и организациям, представляю доверителей в судах и анализирую сложные правовые вопросы."),
        ('content="Я, адвокат Глебова Елена Алексеевна, оказываю правовую помощь',
         'content="Оказываю правовую помощь'),
        ("Я — адвокат Адвокатской палаты Московской области.",
         "Осуществляю адвокатскую деятельность в Адвокатской палате Московской области."),
        ("Меня зовут Елена Алексеевна Глебова. Я — адвокат Адвокатской палаты Московской области. Представляю доверителей в судах, провожу правовую аналитику, проверяю договоры и готовлю правовые позиции.",
         "Осуществляю адвокатскую деятельность в Адвокатской палате Московской области. Представляю доверителей в судах."),
        ("Я, адвокат Глебова Елена Алексеевна, оказываю правовую помощь",
         "Оказываю правовую помощь"),
        ("Юридическая помощь по семейным делам: расторжение брака, раздел имущества, алименты, споры о детях и представляю доверителя в суде.",
         "Правовая помощь по семейным спорам: расторжение брака, раздел имущества, алименты и споры о детях. Представительство в суде."),
        ("Юридическая помощь потребителям: недостатки товаров и услуг, возврат денежных средств, претензии и представляю доверителя в суде.",
         "Правовая помощь потребителям по спорам о недостатках товаров и услуг, возврате денежных средств и претензиям. Представительство в суде."),
        ("Я прошу не направлять мне в первом сообщении подробности дела и документы.",
         "В первом сообщении достаточно обозначить общую категорию вопроса; подробности дела и документы передаются после согласования безопасного способа связи."),
        ("Я отдельно согласую безопасный способ передачи материалов.",
         "Безопасный способ передачи материалов согласуется отдельно."),
        ("Я отдельно согласую с вами безопасный способ передачи материалов.",
         "Безопасный способ передачи материалов согласуется отдельно."),
        ("Я предлагаю сначала обозначить общую категорию правового вопроса",
         "Для начала достаточно обозначить общую категорию правового вопроса"),
        ("Я представляю доверителей в судах и помогаю гражданам и организациям решать сложные правовые вопросы.",
         "Представляю доверителей в судах и помогаю гражданам и организациям решать сложные правовые вопросы."),
        ("Позвонить мне", "Позвонить"),
        ("Написать мне", "Написать"),
        ("Связаться со мной", "Контакты"),
        ("Обсудить со мной правовой вопрос", "Обсудить правовой вопрос"),
        ("Моя практика", "Практика"),
        ("Мои материалы", "Публикации"),
        ("Мои контакты", "Контакты"),
        ("Как я работаю", "Порядок работы"),
        ("Все мои правовые материалы", "Все правовые материалы"),
        ("Посмотреть ориентиры моего вознаграждения", "Ориентиры вознаграждения"),
        ("Налоговые Споры", "Налоговые споры"),
        ("Недвижимость И Земельные Споры", "Недвижимость и земельные споры"),
        ("Трудовые Споры", "Трудовые споры"),
        ("Мои Правовые Материалы", "Правовые материалы"),
        ("Земельное Право И Налоги", "Земельное право и налоги"),
        ("Договорное Право", "Договорное право"),
        ("Арбитраж И Специальные Экономические Меры", "Арбитраж и специальные экономические меры"),
        ("3 500 ₽ .", "3 500 ₽."),
        ("Правовая помощь гражданам и организациям по судебным спорам, договорным и имущественным вопросам, сопровождению и аналитике.",
         "Правовая помощь гражданам и организациям по судебным спорам, договорным и имущественным вопросам, а также в рамках сопровождения и правовой аналитики."),
        ("Правовая помощь гражданам и организациям по вопросам гражданского и арбитражного права, семейным, наследственным и потребительским спорам",
         "Правовая помощь гражданам и организациям по вопросам гражданского и арбитражного права, включая семейные, наследственные и потребительские споры"),
        ("Я использую сайт для первичного контакта по общему вопросу.",
         "Сайт предназначен для первичного обращения по общему вопросу."),
        ("Что я согласую с доверителем", "Что согласуется до начала работы"),
        ("В первом обращении достаточно назвать общую категорию правового вопроса",
         "После первичного сообщения можно согласовать дальнейший формат связи"),
        ("Ссылка открывает мой профиль в MAX. Первое сообщение можно ограничить общей категорией вопроса; документы и подробности дела я прошу передавать только после согласования безопасного способа связи.",
         "Ссылка и QR-код ведут к одному профилю в MAX. В первом сообщении достаточно обозначить общую категорию вопроса."),
        ("Апелляционное и кассационное обжалование оформляются как самостоятельные этапы.",
         "Апелляционное и кассационное обжалование оформляются как самостоятельные этапы."),
    ]
    for old, new in replacements:
        raw = raw.replace(old, new)

    # Keep the biography's introduction factual, without repeating the name or listing work twice.
    if page.as_posix().endswith("about/index.html"):
        raw = raw.replace(
            "Я окончила Московскую государственную юридическую академию в 2000 году",
            "Окончила Московскую государственную юридическую академию в 2000 году",
        )

    # Consolidate repeated wording on the mandate page without changing the legal scope or facts.
    if page.as_posix().endswith("documents/index.html"):
        raw = raw.replace(
            "Я оказываю правовую помощь на основании индивидуального письменного соглашения с доверителем. В соглашении я фиксирую предмет поручения, объём помощи, размер моего вознаграждения, порядок компенсации расходов, ответственность сторон и другие необходимые условия.",
            "Правовая помощь оказывается на основании индивидуального письменного соглашения. В нём закрепляются предмет и границы поручения, состав действий, вознаграждение, порядок компенсации расходов, ответственность сторон и другие необходимые условия.",
        )
        raw = raw.replace(
            "До начала работы я согласую порядок взаимодействия и содержание поручения. Объём помощи определяю с учётом обстоятельств, документов, процессуальной стадии и задач доверителя.",
            "До начала работы обсуждаются обстоятельства, состав документов, процессуальная стадия и задачи доверителя; согласованные действия и порядок взаимодействия закрепляются в соглашении.",
        )
        raw = raw.replace(
            "Я составляю соглашение с учётом предмета и объёма конкретного поручения.",
            "Условия соглашения определяются предметом и объёмом конкретного поручения.",
        )
        raw = raw.replace(
            "Я соблюдаю режим адвокатской тайны и защищаю сведения, полученные в связи с оказанием правовой помощи. Я предлагаю сначала связаться со мной по телефону или электронной почте, чтобы согласовать формат дальнейшего взаимодействия и безопасный способ передачи материалов.",
            "Соблюдаю режим адвокатской тайны и защищаю сведения, полученные в связи с оказанием правовой помощи. Для согласования формата взаимодействия и безопасного способа передачи материалов можно сначала связаться по телефону или электронной почте.",
        )
        raw = raw.replace(
            "Я прошу не направлять по электронной почте без предварительного согласования подробное описание дела, паспортные данные, сведения о здоровье, судебные документы и материалы с персональными данными других лиц. На сайте я не предусматриваю загрузку документов.",
            "Без предварительного согласования не следует направлять по электронной почте подробное описание дела, паспортные данные, сведения о здоровье, судебные документы и материалы с персональными данными других лиц. Загрузка документов на сайте не предусмотрена.",
        )

    # The biography starts with the professional role; the name is already in the page title.
    if page.as_posix().endswith("about/index.html"):
        raw = raw.replace(
            "Меня зовут Елена Алексеевна Глебова. Осуществляю адвокатскую деятельность в Адвокатской палате Московской области. Представляю доверителей в судах, провожу правовую аналитику, проверяю договоры и готовлю правовые позиции.",
            "Осуществляю адвокатскую деятельность в Адвокатской палате Московской области. Представляю доверителей в судах.",
        )
        raw = raw.replace(
            "Я окончила Московскую государственную юридическую академию в 2000 году",
            "Окончила Московскую государственную юридическую академию в 2000 году",
        )

    # The phone conversation and its limits are explained once on the process page.
    if page.as_posix().endswith("working-process/index.html"):
        raw = raw.replace(
            "Безопасный способ передачи материалов согласуется отдельно.</p><p>Само обращение не означает, что я приняла поручение или заключила соглашение.",
            "Само обращение не означает принятия поручения или заключения соглашения.",
        )

    # The same stage-fee note was accidentally repeated in the long pricing explanation.
    if page.as_posix().endswith("remuneration/index.html"):
        repeated = "Апелляционное и кассационное обжалование оформляются как самостоятельные этапы."
        position = raw.rfind(repeated)
        first = raw.find(repeated)
        if position > first >= 0:
            raw = raw[:position] + raw[position + len(repeated):]

    # Remove the explicit pronoun in editorial copy while leaving the first-person verb intact.
    raw = re.sub(r'(>\s*)[Яя]\s+([а-яё])', lambda m: m.group(1) + m.group(2).upper(), raw)
    raw = re.sub(r'([.!?]\s+)[Яя]\s+([а-яё])', lambda m: m.group(1) + m.group(2).upper(), raw)
    raw = re.sub(r'(?<![A-Za-zА-Яа-яЁё0-9_])[Яя]\s+', '', raw)

    # Restore legal examples, answers and article text exactly as authored.
    for marker, block in protected:
        raw = raw.replace(marker, block)
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



def replace_header_contact(raw: str) -> str:
    """Replace the direct-call header CTA with an accessible, no-JS contact menu."""
    pattern = r'<a class="header-call"[^>]*>[\s\S]*?</a>'
    return re.sub(pattern, lambda _: '''<details class="header-contact">
  <summary class="header-call"><span class="call-icon" aria-hidden="true">↗</span><span>Связаться</span><span class="header-contact-caret" aria-hidden="true">⌄</span></summary>
  <div class="header-contact-menu" aria-label="Способы связи">
    <a class="header-contact-option" href="tel:+79104707654"><span class="header-contact-label">Телефон</span><strong>+7 (910) 470-76-54</strong></a>
    <a class="header-contact-option" href="mailto:e_glebova@mail.ru"><span class="header-contact-label">Электронная почта</span><strong>e_glebova@mail.ru</strong></a>
    <a class="header-contact-option" href="https://max.ru/u/f9LHodD0cOIGv2USorbITiorIcZg-hxVehoxHeCMRuY2nJw7PJPJMc7vE-8" target="_blank" rel="noopener noreferrer"><span class="header-contact-label">Мессенджер MAX</span><strong>Открыть профиль для связи ↗</strong></a>
  </div>
</details>''', raw, count=1, flags=re.I)

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
        raw = replace_header_contact(raw)
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
        # Remove legacy footer notes; the distinction is now explained in the relevant page content.
        raw = re.sub(r'<div class="container footer-brief-note">.*?</div>', '', raw, flags=re.S)
        raw = raw.replace("Документы и соглашения", "Оформление поручения")
        # Preserve all seven navigation routes in the HTML; the Contacts item is intentionally hidden in the header to leave room for the call action.
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
        nav_match = re.search(r'(?s)<nav class="primary-nav" aria-label="Основная навигация">.*?</nav>', raw)
        if not nav_match:
            errors.append(f"{rel}: primary navigation is missing")
        else:
            nav_html = nav_match.group(0)
            nav_links = re.findall(r'<a class="nav-link" href=', nav_html)
            if len(nav_links) != 7:
                errors.append(f"{rel}: expected 7 primary navigation anchors in HTML (6 are displayed in the header), found {len(nav_links)}")
            for label in ("Практика", "Цены и оплата", "Порядок работы", "Обо мне", "Оформление поручения", "Публикации", "Контакты"):
                if label not in nav_html:
                    errors.append(f"{rel}: primary navigation label is missing: {label}")
        if '<details class="mobile-nav">' in raw:
            errors.append(f"{rel}: primary navigation must not be hidden in a collapsed disclosure")
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
            if "Предварительная беседа по телефону" not in raw or "бесплатно" not in raw:
                errors.append(f"{rel}: free preliminary phone conversation wording is missing")
            if "не является юридической консультацией" not in raw:
                errors.append(f"{rel}: preliminary conversation must be distinguished from legal consultation")
            if "Юридическая консультация (до 1 часа)" not in raw or "3 500 ₽" not in raw:
                errors.append(f"{rel}: paid legal consultation wording or fee is missing")
            if "Ознакомительная консультация по телефону" in raw:
                errors.append(f"{rel}: preliminary conversation is incorrectly labelled as a consultation")
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
