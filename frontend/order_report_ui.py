"""
Structured Capital Works Order Report UI (Streamlit).
"""

from __future__ import annotations

from typing import Any

import streamlit as st


def render_order_report_panel(vm: dict[str, Any]) -> None:
    """Render report from view model produced by build_order_report_view_model."""
    meta = vm.get("meta", {})
    st.markdown(
        f"""
        <div class="cn-card" style="border-left:3px solid #1de9b6;margin-bottom:1rem">
            <div style="display:flex;flex-wrap:wrap;gap:1.5rem;align-items:center">
                <div>
                    <div class="cn-card-title" style="margin:0">Capital Works Order Report</div>
                    <div style="font-size:.72rem;color:#5a7a9a;margin-top:.25rem">
                        {meta.get("generated_at", "")} · Nemotron W1 + local analytics
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Pipes selected", meta.get("n_sel", 0))
    m2.metric("Annual budget", f"${meta.get('budget', 0):,}")
    m3.metric("Portfolio ROI", f"{meta.get('roi_pct', 0):.0f}%")
    m4.metric("Properties protected", f"{meta.get('sel_props', 0):,}")

    with st.expander("Priority queue", expanded=True):
        st.dataframe(
            vm.get("queue_table"),
            use_container_width=True,
            hide_index=True,
        )

    w1_sections = vm.get("w1_sections") or []
    if w1_sections:
        with st.expander(
            f"Risk intelligence · Nemotron W1 ({len(w1_sections)} segment(s))",
            expanded=True,
        ):
            for block in w1_sections:
                _render_w1_block(block)

    w2_sections = vm.get("w2_sections") or []
    if w2_sections:
        with st.expander("Multi-role analysis · Workflow 2", expanded=False):
            for block in w2_sections:
                st.markdown(f"**{block.get('pipe_id')}** · run `{block.get('run_id', '')}`")
                for line in block.get("actions", []):
                    st.markdown(f"- {line}")
                excerpt = block.get("excerpt")
                if excerpt:
                    st.caption(excerpt)

    fin = vm.get("financial") or {}
    with st.expander("Financial summary & schedule", expanded=False):
        fc1, fc2, fc3, fc4 = st.columns(4)
        fc1.metric("Replacement cost", f"${fin.get('sel_cost', 0):,}")
        fc2.metric("Est. emergency cost", f"${fin.get('emergency_total', 0):,}")
        fc3.metric("Net savings", f"${fin.get('sel_savings', 0):,}")
        fc4.metric("ROI", f"{fin.get('roi_pct', 0):.0f}%")
        for item in vm.get("schedule") or []:
            st.markdown(
                f"- **{item.get('label')}** — {item.get('pipes')} ({item.get('ward')})"
            )

    with st.expander("Full plain-text report (download)", expanded=False):
        st.code(vm.get("plain_text", ""), language=None)


def _render_w1_block(block: dict[str, Any]) -> None:
    pid = block.get("pipe_id", "")
    source = block.get("source", "unknown")
    badge_color = "#1de9b6" if source == "nemotron" else "#ffa726"
    badge_label = "Nemotron W1" if source == "nemotron" else "Template"
    st.markdown(
        f"""
        <div class="cn-card" style="margin-bottom:.75rem;border-left:3px solid {badge_color}">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:.5rem">
                <div class="cn-card-title" style="margin:0">{pid}</div>
                <span style="font-size:.65rem;color:{badge_color};font-weight:600">● {badge_label}</span>
            </div>
            <div style="font-size:.85rem;font-weight:600;color:#c9d8ea;margin:.4rem 0 .2rem">
                {block.get("headline", "")}</div>
            <div style="font-size:.8rem;line-height:1.45;color:#c9d8ea">
                {block.get("risk_sentence", "")}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    reasons = block.get("top_reasons") or []
    if reasons:
        st.markdown("**Drivers**")
        for r in reasons[:5]:
            st.markdown(f"- {r}")
    step = block.get("recommended_next_step")
    if step:
        st.info(f"**Recommended:** {step}")
