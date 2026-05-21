# Troy & Banks — Streamlit frontend

Current production UI for the audit demo. Talks to the FastAPI backend via `BACKEND_URL`.

## Run locally

From the **repository root** (so `data/` paths resolve):

```bash
pip install -r frontend/requirements.txt
export BACKEND_URL=http://127.0.0.1:8000   # or your API port
streamlit run frontend/streamlit3.py
```

Docker: see root `docker-compose.yml` (UI on port 8501, API on 8000/8001).

## Layout

| Path | Role |
|------|------|
| `streamlit3.py` | Entry: theme, session defaults, page routing |
| `config.py` | `.env` / `local.env`, `BACKEND_URL`, data paths |
| `api_client.py` | HTTP helpers, schedule proxies, bills/tariff API |
| `theme.py` | Dark/light CSS, palette, persisted tab control |
| `styles/` | `dark_global.css`, `light_override.css`, Baseweb overrides |
| `pages/` | `upload`, `results`, `ops`, `sidebar` |
| `components/` | Shared UI: tables, anomalies, analysis tabs, ops panels |

### `components/` package

- `tables.py` — DataFrames, Excel export, billing column configs
- `anomalies.py` — Anomaly settings and results section
- `analysis.py` — Rate/schedule compare tabs, usage charges, KPIs
- `ops.py` — Tariff/riders upload, past-usage recalc, export hub
- `__init__.py` — Re-exports for `from components import ...`

Import from the `frontend/` directory (Streamlit sets cwd there), e.g. `from components import render_schedule_compare_tab`.

## Environment

| Variable | Default | Notes |
|----------|---------|--------|
| `BACKEND_URL` | `http://127.0.0.1:8000` | FastAPI base URL |
| `PROJECT_ROOT` | parent of `frontend/` | Used for `data/` paths when set |

Optional: `.env` or `local.env` at repo root (loaded by `config.py`).

## Tests

Backend/API tests live in repo `tests/`. Smoke-compile the frontend:

```bash
python3 -m compileall -q frontend
```
