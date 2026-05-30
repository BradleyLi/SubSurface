"""
app_styles.py — Shared CSS theme injection for CityNerve Streamlit app
Industrial command-center aesthetic: deep navy, electric teal, amber/red danger.
Fonts: Barlow Condensed (headers) · DM Sans (body) · IBM Plex Mono (data values)
"""

import streamlit as st

_CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700;800;900&family=IBM+Plex+Mono:wght@400;500;600&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">

<style>
/* ── Reset & fonts ── */
html, body, [class*="css"], .stApp {
    font-family: 'DM Sans', sans-serif !important;
}

/* ── Hide Streamlit chrome ── */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
.stDeployButton { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }
[data-testid="stToolbar"] { display: none !important; }

/* ── Header bar ── */
[data-testid="stHeader"] {
    background-color: #07101f !important;
    border-bottom: 1px solid #1de9b620 !important;
}

/* ── Sidebar (shown on sub-pages, hidden on main page via inline css) ── */
[data-testid="stSidebarCollapseButton"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }

/* ── Top Nav ── */
.cn-topnav {
    display: flex;
    align-items: center;
    gap: 0;
    padding: 0.5rem 0 0.6rem;
}
.cn-nav-logo {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 1.45rem;
    font-weight: 900;
    color: #e0eaf6;
    letter-spacing: 0.06em;
    line-height: 1;
}
.cn-nav-logo span { color: #1de9b6; }
.cn-nav-sub {
    font-size: 0.6rem;
    color: #3d5a78;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    font-weight: 400;
    margin-left: 0.5rem;
    font-family: 'DM Sans', sans-serif;
}
.cn-nav-divider {
    height: 1px;
    background: linear-gradient(90deg, #1de9b640 0%, #162033 40%, transparent 100%);
    margin: 0.2rem 0 1.4rem;
}

/* Style page links as nav tab items */
[data-testid="stPageLink"] { display: flex !important; align-items: center !important; }
[data-testid="stPageLink"] a {
    color: #5a7a9a !important;
    font-size: 0.8rem !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 500 !important;
    text-decoration: none !important;
    padding: 0.38rem 0.9rem !important;
    border-radius: 6px !important;
    border: 1px solid transparent !important;
    transition: all 0.16s ease !important;
    white-space: nowrap !important;
    display: inline-block !important;
}
[data-testid="stPageLink"] a:hover {
    color: #c9d8ea !important;
    border-color: #1de9b630 !important;
    background: #1de9b608 !important;
}
[data-testid="stPageLink"] a[aria-current="page"] {
    color: #1de9b6 !important;
    border-color: #1de9b640 !important;
    background: #1de9b610 !important;
}

/* ── Section flow headers ── */
.section-flow-header {
    display: flex;
    align-items: center;
    gap: 0.8rem;
    padding: 1.4rem 0 1rem;
    border-top: 1px solid #162033;
    margin-bottom: 0.5rem;
}
.section-flow-num {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.68rem;
    font-weight: 600;
    color: #1de9b6;
    letter-spacing: 0.18em;
    border: 1px solid #1de9b640;
    border-radius: 4px;
    padding: 2px 8px;
    flex-shrink: 0;
}
.section-flow-title {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 1.15rem;
    font-weight: 800;
    color: #e0eaf6;
    letter-spacing: 0.09em;
    text-transform: uppercase;
}
.section-flow-sub {
    font-size: 0.7rem;
    color: #3d5a78;
    font-weight: 400;
    letter-spacing: 0.08em;
    font-family: 'DM Sans', sans-serif;
    margin-left: 0.2rem;
}

/* ── Filter panel ── */
.filter-panel {
    background: #07101f;
    border: 1px solid #162033;
    border-radius: 10px;
    padding: 1rem 1rem 1.2rem;
    position: sticky;
    top: 4rem;
}
.filter-panel .section-title {
    margin-bottom: 0.6rem;
}

/* ── Quick-select pill buttons ── */
.stButton.qs-btn > button {
    background: transparent !important;
    color: #5a7a9a !important;
    border: 1px solid #162033 !important;
    font-size: 0.72rem !important;
    padding: 0.25rem 0.7rem !important;
    border-radius: 20px !important;
    letter-spacing: 0.04em;
}
.stButton.qs-btn > button:hover {
    color: #1de9b6 !important;
    border-color: #1de9b640 !important;
    background: #1de9b608 !important;
    opacity: 1 !important;
}


/* ── Backgrounds ── */
.stApp { background-color: #050b18 !important; }

[data-testid="stSidebar"] {
    background: #07101f !important;
    border-right: 1px solid #162033 !important;
}
[data-testid="stSidebar"] * {
    font-family: 'DM Sans', sans-serif !important;
}

/* ── Sidebar section labels ── */
.sidebar-label {
    font-family: 'Barlow Condensed', sans-serif !important;
    font-size: 0.68rem;
    font-weight: 700;
    color: #1de9b6;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    margin: 1.2rem 0 0.4rem;
}

/* ── Metric cards ── */
[data-testid="metric-container"] {
    background: #0d1b2a !important;
    border: 1px solid #162033 !important;
    border-radius: 10px !important;
    padding: 1rem !important;
}
[data-testid="stMetricValue"] {
    font-family: 'Barlow Condensed', sans-serif !important;
    font-size: 2.1rem !important;
    font-weight: 800 !important;
    color: #1de9b6 !important;
}
[data-testid="stMetricLabel"] {
    color: #5a7a9a !important;
    font-size: 0.7rem !important;
    letter-spacing: 0.1em;
    text-transform: uppercase;
}
[data-testid="stMetricDelta"] svg { display: none; }

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    background: transparent;
    border-bottom: 1px solid #162033;
    gap: 0;
}
.stTabs [data-baseweb="tab"] {
    color: #5a7a9a !important;
    font-family: 'DM Sans', sans-serif;
    font-size: 0.85rem;
    padding: 0.65rem 1.4rem;
    border-bottom: 2px solid transparent !important;
    background: transparent !important;
}
.stTabs [aria-selected="true"] {
    color: #1de9b6 !important;
    border-bottom-color: #1de9b6 !important;
    background: transparent !important;
}
.stTabs [data-baseweb="tab-panel"] { padding-top: 1.2rem; }

/* ── Buttons ── */
.stButton > button {
    background: linear-gradient(135deg, #1de9b6 0%, #00acc1 100%) !important;
    color: #050b18 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 600 !important;
    border: none !important;
    border-radius: 6px !important;
    padding: 0.45rem 1.4rem !important;
    letter-spacing: 0.04em;
    transition: opacity 0.18s ease;
}
.stButton > button:hover { opacity: 0.82 !important; }

/* Danger button variant */
.danger-btn .stButton > button {
    background: linear-gradient(135deg, #ff3d3d 0%, #c62828 100%) !important;
    color: #fff !important;
}

/* ── Selectbox / inputs ── */
[data-testid="stSelectbox"] > div > div,
[data-testid="stMultiSelect"] > div > div {
    background: #0d1b2a !important;
    border-color: #162033 !important;
    color: #c9d8ea !important;
}
.stTextInput input, .stTextArea textarea {
    background: #0d1b2a !important;
    border-color: #162033 !important;
    color: #c9d8ea !important;
    font-family: 'DM Sans', sans-serif !important;
}

/* ── Dataframe / table ── */
[data-testid="stDataFrame"] {
    border: 1px solid #162033 !important;
    border-radius: 8px;
}
.stDataFrame thead th {
    background: #0d1b2a !important;
    color: #1de9b6 !important;
    font-family: 'Barlow Condensed', sans-serif !important;
    font-size: 0.75rem !important;
    letter-spacing: 0.1em;
    text-transform: uppercase;
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: #050b18; }
::-webkit-scrollbar-thumb { background: #162033; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #1de9b6; }

/* ── Divider ── */
hr { border-color: #162033 !important; }

/* ── Expander ── */
[data-testid="stExpander"] {
    background: #0d1b2a !important;
    border: 1px solid #162033 !important;
    border-radius: 8px !important;
}

/* ── Slider ── */
[data-testid="stSlider"] > div > div > div > div {
    background: #1de9b6 !important;
}

/* ── Custom component classes ── */

/* Page header */
.cn-header {
    padding: 0.5rem 0 1.5rem;
    border-bottom: 1px solid #162033;
    margin-bottom: 1.5rem;
}
.cn-wordmark {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 2rem;
    font-weight: 900;
    color: #e0eaf6;
    letter-spacing: 0.06em;
    line-height: 1;
    display: inline-block;
}
.cn-wordmark span { color: #1de9b6; }
.cn-tagline {
    font-size: 0.75rem;
    color: #5a7a9a;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-top: 0.2rem;
}
.cn-badge {
    display: inline-block;
    background: #1de9b6;
    color: #050b18;
    font-size: 0.6rem;
    font-weight: 700;
    padding: 2px 9px;
    border-radius: 20px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    vertical-align: middle;
    margin-left: 0.6rem;
}
.cn-badge-gpu {
    background: #76b900;
    color: #fff;
}

/* Section title */
.section-title {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 0.72rem;
    font-weight: 700;
    color: #1de9b6;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    margin-bottom: 0.8rem;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid #162033;
}

/* Info card */
.cn-card {
    background: #0d1b2a;
    border: 1px solid #162033;
    border-radius: 10px;
    padding: 1.1rem 1.2rem;
    margin-bottom: 0.8rem;
}
.cn-card-title {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 0.68rem;
    font-weight: 700;
    color: #1de9b6;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    margin-bottom: 0.6rem;
}

/* Risk badges */
.risk-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 4px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.04em;
}
.risk-critical { background: rgba(255,61,61,0.15);  color: #ff3d3d; border: 1px solid rgba(255,61,61,0.3); }
.risk-high     { background: rgba(255,167,38,0.15); color: #ffa726; border: 1px solid rgba(255,167,38,0.3); }
.risk-medium   { background: rgba(255,221,87,0.12); color: #ffdd57; border: 1px solid rgba(255,221,87,0.25); }
.risk-low      { background: rgba(29,233,182,0.12); color: #1de9b6; border: 1px solid rgba(29,233,182,0.25); }

/* Pipeline status nodes */
.pipeline-wrap {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.3rem;
    padding: 0.9rem 1rem;
    background: #07101f;
    border: 1px solid #162033;
    border-radius: 10px;
    margin-bottom: 1.5rem;
}
.pipeline-node {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.35rem 0.85rem;
    background: #0d1b2a;
    border: 1px solid #162033;
    border-radius: 5px;
    font-size: 0.78rem;
    color: #5a7a9a;
    font-family: 'IBM Plex Mono', monospace;
    font-weight: 500;
}
.pipeline-node.active {
    border-color: #1de9b6;
    color: #1de9b6;
    box-shadow: 0 0 8px rgba(29,233,182,0.15);
}
.pipeline-node.gpu {
    border-color: #76b900;
    color: #76b900;
}
.node-dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    background: currentColor;
    flex-shrink: 0;
}
.node-dot.pulse {
    animation: pulse 1.8s ease-in-out infinite;
}
@keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50%       { opacity: 0.4; transform: scale(0.7); }
}
.pipeline-arrow { color: #1a2e4a; font-size: 1rem; padding: 0 0.1rem; }

/* Alert row */
.alert-row {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    padding: 0.7rem 0.9rem;
    background: #0d1b2a;
    border: 1px solid #162033;
    border-left: 3px solid #ff3d3d;
    border-radius: 6px;
    margin-bottom: 0.5rem;
    font-size: 0.82rem;
}
.alert-row.warn { border-left-color: #ffa726; }
.alert-row.info { border-left-color: #1de9b6; }
.alert-icon { font-size: 1rem; flex-shrink: 0; line-height: 1.4; }
.alert-text { color: #c9d8ea; line-height: 1.5; }
.alert-text strong { color: #e0eaf6; }
.alert-meta { color: #3d5a78; font-size: 0.72rem; margin-top: 0.15rem; }

/* Data stat */
.data-stat {
    text-align: center;
    padding: 0.6rem;
}
.data-stat .number {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 2rem;
    font-weight: 800;
    color: #e0eaf6;
    line-height: 1;
}
.data-stat .label {
    font-size: 0.68rem;
    color: #5a7a9a;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-top: 0.2rem;
}

/* Chat bubbles */
.chat-user {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 0.9rem;
}
.chat-user .bubble {
    background: #1de9b620;
    border: 1px solid #1de9b640;
    color: #c9d8ea;
    padding: 0.7rem 1rem;
    border-radius: 12px 12px 2px 12px;
    max-width: 80%;
    font-size: 0.88rem;
    line-height: 1.5;
}
.chat-ai {
    display: flex;
    justify-content: flex-start;
    margin-bottom: 0.9rem;
}
.chat-ai .bubble {
    background: #0d1b2a;
    border: 1px solid #162033;
    color: #c9d8ea;
    padding: 0.7rem 1rem;
    border-radius: 12px 12px 12px 2px;
    max-width: 85%;
    font-size: 0.88rem;
    line-height: 1.6;
}
.chat-label {
    font-size: 0.65rem;
    color: #3d5a78;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-bottom: 0.25rem;
    padding: 0 0.25rem;
}

/* Work order output */
.work-order {
    background: #07101f;
    border: 1px solid #1de9b630;
    border-left: 3px solid #1de9b6;
    border-radius: 8px;
    padding: 1.2rem;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.78rem;
    color: #8faabf;
    line-height: 1.8;
    white-space: pre-wrap;
}
.work-order .wo-title {
    color: #1de9b6;
    font-size: 0.82rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
}

/* Gauge label */
.gauge-wrap {
    text-align: center;
}
.gauge-score {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 3rem;
    font-weight: 900;
    line-height: 1;
}
.gauge-label {
    font-size: 0.7rem;
    color: #5a7a9a;
    text-transform: uppercase;
    letter-spacing: 0.12em;
}

/* Impact stat grid */
.impact-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.6rem;
    margin-top: 0.6rem;
}
.impact-item {
    background: #07101f;
    border: 1px solid #162033;
    border-radius: 7px;
    padding: 0.6rem 0.8rem;
    text-align: center;
}
.impact-num {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 1.6rem;
    font-weight: 800;
    color: #e0eaf6;
    line-height: 1;
}
.impact-lbl {
    font-size: 0.65rem;
    color: #5a7a9a;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-top: 0.15rem;
}
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str, badge: str = "") -> None:
    badge_html = (
        f'<span class="cn-badge">{badge}</span>' if badge else ""
    )
    st.markdown(
        f"""
        <div class="cn-header">
            <div class="cn-wordmark">{title}</div>
            {badge_html}
            <div class="cn-tagline">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_title(text: str) -> None:
    st.markdown(f'<div class="section-title">{text}</div>', unsafe_allow_html=True)


def risk_badge(level: str) -> str:
    css = level.lower()
    return f'<span class="risk-badge risk-{css}">{level}</span>'


def alert(text: str, kind: str = "error", icon: str = "●") -> None:
    cls = {"error": "", "warn": "warn", "info": "info"}.get(kind, "")
    st.markdown(
        f"""
        <div class="alert-row {cls}">
            <span class="alert-icon">{icon}</span>
            <span class="alert-text">{text}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
