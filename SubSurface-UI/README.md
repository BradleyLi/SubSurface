# SubSurface-UI

React front-end for CityNerve SubSurface with a **Mapbox GL 3D map** (light mode) as the full-screen background and a sidebar for filters, AI agents, and voice caller reports.

This is the **primary UI** for the demo stack started by `./scripts/run_citynerve.sh`.

## Prerequisites

1. **Full stack** from `SubSurface/` (API + this UI + voice line + Ollama):

   ```bash
   cd ../SubSurface
   cp SubSurface-UI/.env.example SubSurface-UI/.env   # set VITE_MAPBOX_TOKEN
   ./scripts/run_citynerve.sh
   ```

   Or run **API only**, then start the UI yourself:

   ```bash
   uvicorn backend.main:app --host 127.0.0.1 --port 8000
   cd SubSurface-UI && npm install && npm run dev
   ```

2. **Mapbox access token** — [create one free](https://account.mapbox.com/access-tokens/) in `SubSurface-UI/.env`

## Setup (UI only)

```bash
cd SubSurface-UI
cp .env.example .env
# Edit .env: VITE_MAPBOX_TOKEN=pk....
npm install
npm run dev
```

Open http://localhost:5173 (or the `UI_PORT` from `run_citynerve.sh`)

The Vite dev server proxies `/api` and `/health` to `http://127.0.0.1:8000`, and `/voice-events` to the voice server (default `:8504`).

## Features

- **3D Mapbox map** — `light-v11` style, 55° pitch, terrain DEM, fog
- **Pipe network overlay** — risk-colored line segments from `/api/pipes`
- **Sidebar filters** — risk level, material, ward, pipe type, min risk score
- **Critical Priority Queue** — top 100 critical pipes by network percentile
- **Click-to-inspect** — select a pipe on map or table to fly-to and view details
- **Workflow 1 (Summary Agent)** — Nemotron JSON risk summary on pipe select
- **Workflow 2 (Multi-Role Analysis)** — Engineer/Police/Field/Operations + synthesis + BoM
- **Voice integration** — caller report alert, map marker, SSE refresh, W2 transcript context

## Production build

```bash
npm run build
npm run preview
```

For production, ensure the FastAPI backend allows CORS from your UI origin, or serve the built assets behind the same reverse proxy as the API.
