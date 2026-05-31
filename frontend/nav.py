"""
Shared top navigation for Streamlit pages (sidebar hidden).
"""

from __future__ import annotations

import streamlit as st

# Display order for hackathon flow (paths are Streamlit page_link targets).
NAV_PAGES: list[dict[str, str]] = [
    {"id": "overview", "label": "Overview", "path": "app.py"},
    {"id": "risk_map", "label": "Risk Map", "path": "pages/1_Risk_Map.py"},
    {"id": "decision", "label": "Decision Engine", "path": "pages/2_Decision_Engine.py"},
    {"id": "cascade", "label": "Cascade Sim", "path": "pages/3_Cascade_Simulator.py"},
    {"id": "ai", "label": "AI Assistant", "path": "pages/4_AI_Assistant.py"},
    {"id": "watermains", "label": "Watermains", "path": "pages/5_Distribution_Watermain.py"},
]

HIDE_SIDEBAR_CSS = """
<style>
[data-testid="stSidebar"] { display: none !important; }
[data-testid="stSidebarNav"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }
</style>
"""


def hide_sidebar() -> None:
    st.markdown(HIDE_SIDEBAR_CSS, unsafe_allow_html=True)


def render_top_nav(
    current: str,
    *,
    show_data_toggle: bool = True,
    use_real_key: str = "use_real_data",
) -> bool:
    """
    Render CityNerve top nav. Returns current use_real toggle value.

    current: page id from NAV_PAGES (e.g. "risk_map", "overview").
    """
    hide_sidebar()

    logo_col, gap_col, *nav_cols, toggle_col = st.columns(
        [2.6, 0.2] + [1.05] * len(NAV_PAGES) + [2.2]
    )

    with logo_col:
        st.markdown(
            '<div class="cn-topnav"><div class="cn-nav-logo">CITY<span>NERVE</span>'
            '<span class="cn-nav-sub"> SubSurface Intelligence</span></div></div>',
            unsafe_allow_html=True,
        )

    for col, page in zip(nav_cols, NAV_PAGES):
        with col:
            label = page["label"]
            if page["id"] == current:
                label = f"▸ {label}"
            st.page_link(page["path"], label=label)

    use_real = st.session_state.get(use_real_key, False)
    if show_data_toggle:
        with toggle_col:
            use_real = st.toggle(
                "Toronto Open Data",
                value=use_real,
                key=use_real_key,
                help="Live Toronto Open Data vs synthetic demo pipes",
            )

    st.markdown('<div class="cn-nav-divider"></div>', unsafe_allow_html=True)
    return use_real


def w1_session_key(pipe_id: str) -> str:
    return f"w1_summary_{pipe_id}"


def w2_session_key(pipe_id: str) -> str:
    return f"w2_run_{pipe_id}"
