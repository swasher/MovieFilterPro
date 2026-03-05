# Front Template (из PDF Vault)

Этот шаблон содержит только фронтовый каркас:
- общий layout;
- header с кнопками (`PDF`, `Upload`, `Settings`, поиск, тема, login);
- sidebar со структурой разделов/подразделов;
- стиль в духе текущего проекта.

Ручная сортировка в sidebar намеренно удалена.

## Что копировать в новый проект

1. Папку `src` из этого каталога:
   - `src/routes/+layout.svelte`
   - `src/routes/+page.svelte`
   - `src/routes/layout.css`
   - `src/lib/components/AppShell.svelte`
   - `src/lib/template-data.ts`
2. Убедиться, что в новом проекте есть `tailwindcss` v4 и `tw-animate-css`.

## Минимальные зависимости

```bash
pnpm add -D tailwindcss tw-animate-css
```

Если проект уже на SvelteKit + Tailwind 4, обычно этого достаточно.

## Адаптация под новый проект

- Меню header меняется в `src/lib/template-data.ts` (`headerLinks`).
- Пункты sidebar меняются там же (`sidebarItems`).
- Название приложения задается в `src/routes/+layout.svelte` через `appName`.
- Контент страниц вставляется в обычные route-файлы, layout уже готов.
