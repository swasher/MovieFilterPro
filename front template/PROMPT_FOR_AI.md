Скопируй в мой новый SvelteKit проект фронтовый шаблон из папки `front template/src`:

- подключи `src/routes/+layout.svelte` и `src/routes/layout.css`;
- добавь `src/lib/components/AppShell.svelte` и `src/lib/template-data.ts`;
- оставь хедер (PDF/Upload/Settings, поиск, тема, login) и боковую панель;
- не добавляй drag-and-drop или ручную сортировку в sidebar;
- сохрани адаптивное поведение (sidebar drawer на mobile);
- текущие страницы проекта заверни в этот layout.

Если в проекте нет зависимостей для стилей, установи:
`pnpm add -D tailwindcss tw-animate-css`
