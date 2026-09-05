# Frontend — Revenue Recovery Ops Center

Vite + React + TypeScript. Dark glassmorphism, `framer-motion` for motion, `recharts`
for the scoreboard. No CSS framework — the design system is `src/styles.css`.

```bash
npm install
npm run dev        # http://localhost:5173  (expects the backend on :8000)
npm run build      # -> dist/
```

Point at a non-default backend with `VITE_API=http://host:port npm run dev`.

- `src/api.ts` — REST helpers, `useEventStream` (SSE), `usePoll`
- `src/components.tsx` — every panel
- `src/App.tsx` — layout
