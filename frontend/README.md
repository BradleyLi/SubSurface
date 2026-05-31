# Frontend

Streamlit user interface for CityNerve.

Current UI entry points remain at repository root for Streamlit multipage compatibility:
- `app.py`
- `pages/`

Shared modules:
- `nav.py` — top navigation (`NAV_PAGES` order) and sidebar hide
- `workflow1_ui.py` — Workflow 1 cards (parallel fetch, template preview)
- `order_report_ui.py` — structured capital works order report panel
- `report.py` — capital works report and work orders (Nemotron W1 + optional W2 from session)

Page order (sidebar hidden): Overview → Risk Map → Decision Engine → Cascade → AI → Watermains.
