# AGENTS.md — Frontend (Svelte)

## Обязательные правила
- Работать только в `front/`.
- Использовать только Svelte 5 syntax с runes (`$state`, `$derived`, `$effect`, `$props`, snippets и т.д.).
- Не использовать устаревший синтаксис Svelte 3/4.
- Все UI-элементы (кнопки, списки, поля ввода, контейнеры и пр.) строить на базе `shadcn-svelte` компонентов.
- Для нового UI не использовать произвольные raw HTML-кнопки/инпуты, если есть соответствующий компонент `shadcn-svelte`.

## Каркас
- Базовый shell берется из `front template` и адаптируется под проект в `front/`.
- Обязательно сохранить:
  - Header с действиями (PDF, Upload, Settings), поиск, тема, login.
  - Sidebar со структурой разделов/подразделов.
  - Адаптивное поведение (drawer/sidebar на mobile).
- Не добавлять drag-and-drop и ручную сортировку sidebar.

## Технический стек
- SvelteKit + Svelte 5 (runes only).
- `shadcn-svelte` как обязательная UI-база.
- Backend API для нового фронта: `django-ninja`.
