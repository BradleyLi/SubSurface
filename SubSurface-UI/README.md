# SubSurface-UI

React front-end for CityNerve SubSurface with a **Mapbox GL 3D map** (light mode) as the full-screen background and a sidebar for filters plus a critical-priority pipe table.

The existing Streamlit app in `../SubSurface/` is unchanged.

## Prerequisites

1. **CityNerve API** running (from `SubSurface/`):

   ```bash
   cd ../SubSurface
   ./scripts/run_citynerve.sh
   # or: uvicorn backend.main:app --host 127.0.0.1 --port 8000
   ```

2. **Mapbox access token** — [create one free](https://account.mapbox.com/access-tokens/)

## Setup

```bash
cd SubSurface-UI
cp .env.example .env
# Edit .env and set VITE_MAPBOX_TOKEN=pk....

npm install
npm run dev
```

Open http://localhost:5173

The Vite dev server proxies `/api` and `/health` to `http://127.0.0.1:8000`.

## Features

- **3D Mapbox map** — `light-v11` style, 55° pitch, terrain DEM, fog
- **Pipe network overlay** — risk-colored line segments from `/api/pipes`
- **Sidebar filters** — risk level, material, ward, pipe type, min risk score
- **Critical Priority Queue** — top 100 critical pipes by network percentile
- **Click-to-inspect** — select a pipe on map or table to fly-to and view details

## Production build

```bash
npm run build
npm run preview
```

For production, ensure the FastAPI backend allows CORS from your UI origin, or serve the built assets behind the same reverse proxy as the API.
