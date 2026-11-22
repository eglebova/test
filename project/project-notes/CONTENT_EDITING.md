# Редактирование контента

## Где находится текст

Все страницы — отдельные HTML-файлы. Это позволяет редактировать содержание без отдельной CMS и без сборки JavaScript-приложения. После изменения текста обязательно заново запустить `python3 scripts/build.py --origin https://ваш-домен.ru`.

| Раздел | Файл |
|---|---|
| Главная | `index.html` |
| Обо мне | `about/index.html` |
| Вознаграждение | `remuneration/index.html` |
| Каталог практики | `practice/index.html` |
| Арбитражные споры | `practice/arbitrazhnye-spory/index.html` |
| Семейные споры | `practice/semeinye-spory/index.html` |
| Наследственные споры | `practice/nasledstvennye-spory/index.html` |
| Защита прав потребителей | `practice/zashchita-prav-potrebiteley/index.html` |
| Недвижимость и земельные споры | `practice/nedvizhimost-i-zemelnye-spory/index.html` |
| Трудовые споры | `practice/trudovye-spory/index.html` |
| Налоговые споры | `practice/nalogovye-spory/index.html` |
| Правовая аналитика | `practice/pravovaya-analitika/index.html` |
| Сопровождение бизнеса | `practice/pravovoe-soprovozhdenie-biznesa/index.html` |
| Порядок работы | `working-process/index.html` |
| Вознаграждение | `remuneration/index.html` |
| Документы | `documents/index.html` |
| Контакты | `contacts/index.html` |

## Визуальные настройки

Все цвета, сетки, размеры шрифта и responsive breakpoints находятся в `assets/site.css`. Переменные палитры заданы в `:root`.

## Меню и URL

При создании новой публичной страницы нужно:

1. создать каталог с `index.html` или отдельный `.html`;
2. добавить ссылку на него в меню/подвал/соответствующий контекстный блок;
3. убедиться, что `scripts/build.py` копирует этот каталог (при необходимости расширить `PUBLIC_ITEMS`);
4. повторно запустить сборку и проверить sitemap.

Не создавать thin/doorway-страницы под города и не публиковать направления без фактического подтверждения.


## Публикация и навигация

На хостинг загружается только содержимое `dist/`. В настройках веб-сервера должен быть индексный документ `index.html`; примеры конфигураций находятся в `deploy/` и `.htaccess`. Файловое хранилище или файловый менеджер не является веб-хостингом и не будет автоматически открывать HTML-разделы как страницы сайта.

## Публикации и ссылки MAX (15.11.2026)

Статьи находятся в `articles/<slug>/index.html`, каталог статей — в `articles/index.html`. Новые направления практики находятся в `practice/nedvizhimost-i-zemelnye-spory/`, `practice/trudovye-spory/` и `practice/nalogovye-spory/`. Перед изменением правового текста проверяйте первичный источник и дату; разделяйте позицию суда, нормативный текст и авторский комментарий. MAX URL хранится в разметке как `https://max.ru/u/f9LHodD0cOIGv2USorbITiorIcZg-hxVehoxHeCMRuY2nJw7PJPJMc7vE-8`; QR-файл — `assets/max-contact-card.webp`.
