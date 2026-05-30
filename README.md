# SubSurface — CityNerve

Predictive Infrastructure Intelligence for Toronto's Watermain Network.  
GPU-accelerated (NVIDIA RAPIDS) pipeline that predicts watermain failures, explains risk factors, and simulates cascade effects to optimize municipal capital expenditure.  
Built for the NVIDIA Spark Hackathon — Toronto.

## Running Backend + UI

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

In a second terminal:

```bash
# Optional if you run API elsewhere:
# export CITYNERVE_API_URL="http://127.0.0.1:8000"
streamlit run app.py
```

## Project Structure

```text
SubSurface/
├── frontend/        # shared frontend modules (new)
├── backend/         # FastAPI service
├── model/           # risk/model logic
├── agent/           # human-readable agent narratives
├── app.py           # Streamlit main page (entrypoint)
└── pages/           # Streamlit multipage views
```

Notes:
- `app.py` and `pages/` stay at root to preserve Streamlit multipage discovery.
- New model logic lives in `model/risk_profile.py`.
- New agent narrative logic lives in `agent/why_failing_agent.py`.

## UI Pages

| Page | Description |
|---|---|
| `app.py` | Command Center — KPIs, pipeline status, top critical pipes |
| `pages/1_Risk_Map.py` | Interactive risk map — pipe segments coloured by 12-month break probability + SHAP explainability |
| `pages/2_Cascade_Simulator.py` | Cascade Failure Simulator — "If pipe X breaks, what goes down?" |
| `pages/3_Decision_Engine.py` | Priority queue — ranked replacement list, cost-benefit analysis, Nemotron work order generator |
| `pages/4_AI_Assistant.py` | AI chat interface — NIM/Nemotron natural language Q&A |

## Tech Stack

- **Data**: 10+ Open Data Toronto datasets fused via RAPIDS cuDF + cuSpatial
- **ML**: cuML XGBoost — predicts P(break within 12 months) per pipe segment
- **Graph**: cuGraph — cascade failure propagation through pipe network
- **Explainability**: cuML SHAP — feature contributions per prediction
- **Agent**: NIM / Nemotron — natural language work orders and what-if analysis
- **UI**: Streamlit + Plotly
