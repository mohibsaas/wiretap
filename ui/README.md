# wiretap UI

Local ops dashboard (Vite + React + Tailwind + shadcn-style components, light theme).

FastAPI/uvicorn ship with the core Python package (`uv sync` is enough).

## Dev

```bash
# terminal 1
uv sync
uv run wiretap ui run --no-open

# terminal 2
cd ui && npm install && npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:8787`.

## Production build (served by `wiretap ui run`)

```bash
cd ui && npm install && npm run build
```

Output lands in `src/wiretap/ui/static/`.
