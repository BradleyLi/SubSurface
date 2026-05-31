# SubSurface: Product & Technical Specification
**Project:** Predictive Infrastructure Intelligence for Municipal Water Networks
**Event:** NVIDIA Spark Hack - Toronto
**Tech Stack:** NVIDIA DGX Spark, Nemotron, RAPIDS (cuDF, cuSpatial, cuML, cuGraph), Python, React, Mapbox GL JS.

---

## 1. Executive Summary
**The Problem:** The City of Toronto manages 6,100km of aging watermains reactively. Planners lack the computational ability to cross-reference infrastructure age with environmental stressors (tree roots, utility cuts, frost) to predict breaks or simulate downstream cascade failures.
**The Solution:** SubSurface is an autonomous infrastructure intelligence engine. It fuses 10+ open datasets in GPU memory, translates hidden stressors into quantifiable failure probabilities, simulates network cascade effects, and utilizes an AI Agent to orchestrate proactive capital maintenance.
**The "Spark" Edge:** Local inference on the DGX Spark (128GB Unified Memory) bypasses cloud privacy hurdles and allows massive geospatial data tables to reside in VRAM alongside the Nemotron LLM, eliminating CPU/GPU memory-transfer bottlenecks.
**Demo Strategy:** The live demo is intentionally geofenced to one high-impact neighborhood scenario for reliability and speed, while the backend data pipeline and model execution remain citywide-capable.

---

## 2. System Architecture

The system follows a strict Decoupled Agentic Architecture. 

* **The Data Plane (NVIDIA RAPIDS):** Heavy-lifting computation, spatial joins, and ML inference.
* **The Control Plane (Nemotron Agent):** A ReAct (Reason + Act) state machine that routes queries to the Data Plane.
* **The UI Plane:** Interactive mapping and intelligence feed.

### Architecture Flow
`User Input (UI)` ➔ `Agent State Machine` ➔ `Thought Process` ➔ `Tool Call (RAPIDS API)` ➔ `Observation (Data Return)` ➔ `Final Rationale` ➔ `UI Update`

---

## 3. Data Pipeline & Schema (The "Toolbox" Backend)

### 3.1 Datasets & Ingestion (`cuDF`)
Data is ingested directly into VRAM using `cudf.read_csv` and `cudf.read_json`.
1.  **Target:** Watermain Breaks (Historical labeled data).
2.  **Base Grid:** Watermains (Material, Diameter), Sewer Gravity Mains.
3.  **Stressors:** Street Tree Data (DBH, Species), Rain Gauge Precipitation.
4.  **Disturbances:** Utility Cut Permits, Active Building Permits, Road Resurfacing.
5.  **Leading Indicators:** 311 Service Requests (Water Leaks/Pressure), Lead Water Samples.

### 3.2 Geospatial Processing (`cuSpatial`)
Instead of sequential bounding boxes, parallel GPU threads calculate spatial intersections.
* **Pipe Snapping:** Bind historical break X/Y coordinates to the nearest pipe polyline within a 15m radius.
* **Biological Buffer:** Count trees with DBH > 30cm within a 5m radius of each pipe segment.
* **Vibration Buffer:** Flag pipes within 50m of a Utility Cut Permit issued in the trailing 6 months.

---

## 4. Machine Learning & Graph Simulation

### 4.1 Predictive Engine (`cuML` XGBoost)
* **Goal:** Predict the probability of a specific pipe segment failing in the next 12 months.
* **Features:** `Material` (Categorical), `Diameter`, `Tree_Count_5m`, `Days_Since_Utility_Cut`, `311_Complaint_Density`, `Precipitation_30d`.
* **Explainability (SHAP):** Output feature importance weights for every prediction so the AI agent can explain *why* a pipe is failing (e.g., "Cast Iron + Roots").

### 4.2 Topological Vulnerability Proxy (`cuGraph`)
* **Goal:** Calculate the "Cost of Inaction".
* **Execution:** Treat the watermain grid as a Directed Graph (Edges = pipes, Nodes = intersections/valves). If an edge is removed (rupture), perform a Breadth-First Search (BFS) to approximate downstream impact propagation.
* **Output:** Number of residential/commercial properties affected.
* **Terminology Guardrail:** This is a rapid triage heuristic for prioritization, not a fluid-physics hydraulic solver (e.g., EPANET).

---

## 5. Agentic Framework (The Control Plane)

**Core Principle:** Pure Python State Machine. No bloated frameworks (LangChain/LlamaIndex) to ensure maximum control and zero black-box errors on the local DGX Spark.

### 5.1 System Prompt
> "You are the Chief Infrastructure Engineer for the City of Toronto. Your goal is to evaluate watermain risk, explain vulnerabilities using SHAP data, and simulate cascade failures to justify preventative capital expenditure. You must follow the Thought/Action/Observation loop. Do not hallucinate metrics; only use data returned by your tools."

### 5.2 Tool Registry (Functions exposed to Nemotron)
1.  `query_recent_stressors(location: str) -> dict`: Uses cuSpatial to find recent utility cuts or 311 complaints near a street.
2.  `analyze_pipe_risk(pipe_id: str) -> dict`: Calls cuML XGBoost and returns the Risk Score (Float) and SHAP drivers.
3.  `simulate_cascade_failure(pipe_id: str) -> dict`: Calls cuGraph and returns downstream properties affected and estimated emergency cost.
4.  `draft_work_order(pipe_id: str, justification: str, cost: float) -> str`: Formats a municipal dispatch ticket.

### 5.3 Agent Reliability Contract
* Nemotron must emit strict JSON actions only (no freeform calculations).
* All deterministic logic, math, ranking, and simulation run in Python tools.
* UI includes an expandable "Reasoning Trace" showing Thought -> Action -> Observation logs to prove tool-driven orchestration.

---

## 6. UI/UX Workflow (The Demo Experience)

**Frontend Tech:** React (SubSurface-UI) + Mapbox GL JS.
**Golden Path Scope:** The live UI is geofenced to one dramatic, decision-critical neighborhood scenario (e.g., high-risk pipe near critical services) to guarantee smooth demo execution.

1.  **The Briefing:** Sidebar displays Nemotron's proactive alert based on overnight data (e.g., "14 new Utility Cuts detected on Bloor St.").
2.  **Visual Triage:** Map displays the network. High-risk pipes glow red.
3.  **Interrogation:** User clicks a red pipe. Sidebar displays Nemotron's natural language summary of the SHAP drivers ("Risk elevated due to Cast Iron + mature Oak roots + recent excavation").
4.  **"What-If" Trigger:** User clicks `[Simulate Rupture]`. Map animates a topological impact spread to surrounding blocks (cuGraph output).
5.  **Agent Transparency:** User opens `[Reasoning Trace]` to inspect Thought -> Action -> Observation events and raw tool returns.
6.  **Resolution:** User clicks `[Generate Work Order]`. Agent drafts the preventative maintenance ticket.

---

## 7. Implementation Plan (Hackathon Weekend)

### Saturday: Parallel Development & The Mock Handoff
* **First 60 Minutes (Mandatory Pre-Flight):** Standardize all geospatial datasets to `EPSG:4326` and validate CRS compatibility before any joins.
* **Data Eng 1 (Spatial):** Build `cuDF` ingestion and `cuSpatial` buffers. Start on 1-2 wards for fast iteration, then scale to broader city slices once stable.
* **Data Eng 2 (ML/Graph):** Start immediately using *mock data*. Build XGBoost training loop, SHAP explainer, and basic cuGraph BFS. Merge with Data Eng 1 at 1:00 PM.
* **Agent Eng:** Write the Python ReAct `while` loop. Test Nemotron prompts using hardcoded JSON tool responses. Do not wait for the real ML models.
* **UI Eng:** Stand up MapLibre. Wire up the interactive sidebar. 

### Sunday: Integration & Polish
* **Morning:** Connect the Agent Python loop to the real RAPIDS API endpoints. Connect the UI to the Agent.
* **Afternoon:** Rehearse the exact demo script. Benchmark RAPIDS performance vs CPU Pandas to secure the NVIDIA Ecosystem score.

## 8. Evaluation & Judging Readiness

### 8.1 Predictive Credibility
* Avoid reporting generic accuracy due to class imbalance.
* Primary metric: `Top-K Recall` on held-out historical break windows.
* Baseline: oldest-pipe heuristic for direct comparison.
* Demo narrative example: "Top 100 predicted-risk pipes captured substantially more true breaks than age-only ranking."

### 8.2 NVIDIA "Spark Story" Evidence
* Report at least one reproducible GPU vs CPU benchmark for ingestion + spatial joins + inference.
* Tie gains directly to DGX Spark 128GB Unified Memory and local inference/privacy constraints.
