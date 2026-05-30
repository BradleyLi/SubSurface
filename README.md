# SubSurface — CityNerve

Predictive Infrastructure Intelligence for Toronto's Watermain Network.  
GPU-accelerated (NVIDIA RAPIDS) pipeline that predicts watermain failures, explains risk factors, and simulates cascade effects to optimize municipal capital expenditure.  
Built for the NVIDIA Spark Hackathon — Toronto.

## Running the UI

```bash
pip install -r requirements.txt
streamlit run app.py
```

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
