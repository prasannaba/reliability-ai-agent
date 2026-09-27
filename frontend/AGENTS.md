You are an expert in TypeScript, React, and scalable web application development. You write functional, maintainable, performant, and accessible code following React and TypeScript best practices.

## TypeScript Best Practices

- Use strict type checking
- Prefer type inference when the type is obvious
- Avoid the `any` type; use `unknown` when type is uncertain

## React Best Practices

- Use function components with hooks; no class components
- Use `useState` for local state, `useMemo`/`useCallback` for derived values and stable callbacks
- Keep components small and focused on a single responsibility
- Colocate state as low as possible; lift only what siblings need
- Do not run side effects during render — use `useEffect` with a correct dependency array
- Clean up subscriptions, timers, and animation frames in effect teardowns

## Accessibility Requirements

- It MUST pass all AXE checks.
- It MUST follow all WCAG AA minimums, including focus management, color contrast, and ARIA attributes.

### Components

- Keep components small and focused on a single responsibility
- Keep JSX simple; extract helpers for complex rendering logic
- Prefer controlled inputs
- Use `aria-label`/`aria-pressed`/`role` on icon-only buttons

## State Management

- Keep state transformations pure and predictable
- Prefer functional updates (`setState((prev) => ...)`) when the next value depends on the previous one
- Do not mutate state objects in place

## Styling

- Global theme tokens live in `src/styles.css` (`:root` + `[data-theme="dark"]`); add new colors as tokens, not hardcoded values
- Every new color token needs both a light and a dark value

## Services

- Design services around a single responsibility
- Keep HTTP/streaming details inside `src/services`; components consume the `BackendService` interface
