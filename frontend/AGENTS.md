# Frontend

Next.js 16 App Router in `src/app`, React 19, TypeScript, Tailwind CSS 4, TanStack Query, Zod, next-intl.

## Structure

- `src/app/` — route groups and layouts.
- `src/components/` — product and UI components.
- `src/lib/api/` — typed API hooks; `src/lib/api-client.ts` owns transport/auth refresh.
- `messages/` — Russian and English translations.
- `src/stores/` — client stores only when server/query state is unsuitable.

## Rules

- Use `bun`; never npm or yarn.
- Use React Query for remote state and Zod at API boundaries.
- Avoid direct `useEffect`; derive state, use event handlers/query hooks, or `useMountEffect` for mount-only synchronization.
- All user-facing copy goes through next-intl. Russian is primary; update both locale files.
- Preserve PRODUCT/DESIGN visual language and token variables. No hard-coded semantic colors.
- Keep touch targets at least 44px and support reduced motion.
- Invalidate/remove both list and per-id query caches after mutations.

## Verify

```bash
cd frontend
bun run test --run
bun run typecheck
bun run lint
bun run build
```
