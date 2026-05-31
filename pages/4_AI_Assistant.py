"""
pages/4_AI_Assistant.py — Nemotron / NIM Natural Language Interface
Ask CityNerve about risk, replacement priorities, cascade scenarios, and what-ifs.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import time

st.set_page_config(
    page_title="AI Assistant · CityNerve",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from app_styles import inject_css, section_title
from api_client import get_ai_response_api, get_pipes_api
from frontend.nav import render_top_nav

inject_css()

use_real = render_top_nav("ai")
df = get_pipes_api(use_real=use_real)

# ── Session state ─────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.messages.append({
        "role": "assistant",
        "content": (
            f"**CityNerve AI Online** — powered by NIM / Nemotron\n\n"
            f"I'm monitoring **{len(df):,} pipe segments** across Toronto's watermain network. "
            f"I can answer questions about failure risk, replacement priorities, cascade impacts, "
            f"and what-if scenarios.\n\n"
            f"Try one of the quick actions below or ask me anything."
        ),
    })

# ── Header + Controls row ─────────────────────────────────────────────────────
st.markdown(
    """
    <div class="cn-header">
        <div style="display:flex;align-items:baseline;gap:.8rem">
            <div class="cn-wordmark">🤖  AI <span>ASSISTANT</span></div>
            <span class="cn-badge">NIM / NEMOTRON</span>
            <span class="cn-badge" style="background:#76b900;color:#fff">NVIDIA</span>
        </div>
        <div class="cn-tagline">
            Natural language interface · Explain risk · Generate work orders · Answer what-if scenarios
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Inline controls (were in sidebar)
ctrl1, ctrl2, ctrl3, ctrl4 = st.columns([2, 2, 1.5, 1], gap="medium")
with ctrl1:
    focus_ward = st.selectbox(
        "Focus on Ward",
        options=["All Wards"] + sorted(df["ward"].unique()),
    )
with ctrl2:
    focus_material = st.selectbox(
        "Focus on Material",
        options=["All Materials"] + sorted(df["material"].unique()),
    )
with ctrl3:
    st.markdown(
        """
        <div class="cn-card" style="padding:.55rem .9rem;margin-top:.05rem">
            <div style="display:flex;align-items:center;gap:.5rem">
                <div style="width:7px;height:7px;border-radius:50%;background:#1de9b6;
                            animation:pulse 1.8s ease-in-out infinite;flex-shrink:0"></div>
                <span style="font-family:'IBM Plex Mono',monospace;font-size:.75rem;
                             color:#1de9b6">Nemotron-3</span>
            </div>
            <div style="font-size:.65rem;color:#3d5a78;margin-top:.2rem">
                NVIDIA NIM · Infrastructure Q&A
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with ctrl4:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🗑 Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

st.markdown("<br>", unsafe_allow_html=True)

# ── Quick Action Buttons ───────────────────────────────────────────────────────
section_title("Quick Actions")

qa_cols = st.columns(4)
quick_actions = [
    ("📊 Network Summary",          "Give me a full summary of the current network risk status."),
    ("🔧 Replacement Priority",     "Which pipes should we replace first to maximise savings?"),
    ("💥 Cascade Analysis",         "What happens if the highest-risk pipe fails?"),
    ("🌧️ Winter What-If",          "What if a severe winter freeze-thaw cycle hits the network?"),
]

for col, (label, query) in zip(qa_cols, quick_actions):
    with col:
        if st.button(label, use_container_width=True, key=f"qa_{label}"):
            st.session_state.messages.append({"role": "user", "content": query})
            st.rerun()

st.markdown("<br>", unsafe_allow_html=True)

# ── Chat area ─────────────────────────────────────────────────────────────────
chat_col, context_col = st.columns([3, 1], gap="large")

with chat_col:
    section_title("Conversation")

    # Render all messages
    chat_html = '<div style="max-height:500px;overflow-y:auto;padding:.2rem 0">'
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            chat_html += f"""
            <div class="chat-user">
                <div>
                    <div class="chat-label" style="text-align:right">You</div>
                    <div class="bubble">{msg["content"]}</div>
                </div>
            </div>"""
        else:
            # Convert markdown-ish formatting for HTML display
            content = msg["content"]
            chat_html += f"""
            <div class="chat-ai">
                <div>
                    <div class="chat-label">🤖 Nemotron</div>
                    <div class="bubble">{content}</div>
                </div>
            </div>"""
    chat_html += "</div>"

    # Check if latest message is from user and needs a response
    needs_response = (
        st.session_state.messages
        and st.session_state.messages[-1]["role"] == "user"
    )

    if needs_response:
        last_query = st.session_state.messages[-1]["content"]

        with st.spinner("Nemotron processing..."):
            time.sleep(0.9)
            ai_reply = get_ai_response_api(
                query=last_query,
                use_real=st.session_state.get("use_real_data", True),
                focus_ward=focus_ward,
                focus_material=focus_material,
            )

        st.session_state.messages.append({"role": "assistant", "content": ai_reply})
        st.rerun()

    st.markdown(chat_html, unsafe_allow_html=True)

    # Input field
    st.markdown("<br>", unsafe_allow_html=True)
    with st.form("chat_input", clear_on_submit=True):
        input_cols = st.columns([5, 1])
        with input_cols[0]:
            user_input = st.text_input(
                "Message",
                placeholder="Ask about pipe risk, replacements, cascade failures, what-if scenarios...",
                label_visibility="collapsed",
            )
        with input_cols[1]:
            submitted = st.form_submit_button("Send →", use_container_width=True)

        if submitted and user_input.strip():
            st.session_state.messages.append({"role": "user", "content": user_input.strip()})
            st.rerun()

# ── Context Panel ────────────────────────────────────────────────────────────
with context_col:
    section_title("Network Context")

    # Apply same filter for context stats
    ctx = df.copy()
    if focus_ward != "All Wards":
        ctx = ctx[ctx["ward"] == focus_ward]
    if focus_material != "All Materials":
        ctx = ctx[ctx["material"] == focus_material]

    critical_n = int((ctx["risk_level"] == "Critical").sum())
    high_n     = int((ctx["risk_level"] == "High").sum())
    avg_risk   = ctx["risk_score"].mean() if len(ctx) else 0
    top_pipe   = ctx.nlargest(1, "risk_score").iloc[0] if len(ctx) else None

    st.markdown(
        f"""
        <div class="cn-card">
            <div class="cn-card-title">Active Context</div>
            <div style="font-size:.78rem;color:#8faabf;margin-bottom:.4rem">
                {'All wards' if focus_ward=='All Wards' else focus_ward} ·
                {'All materials' if focus_material=='All Materials' else focus_material}
            </div>
            <div style="font-size:.82rem;color:#c9d8ea">
                {len(ctx):,} segments · avg risk {avg_risk:.1f}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="cn-card">
            <div class="cn-card-title">Risk Summary</div>
            <div style="display:flex;justify-content:space-between;padding:.25rem 0;
                        border-bottom:1px solid #0d1b2a;font-size:.8rem">
                <span style="color:#ff3d3d">● Critical</span>
                <span style="color:#e0eaf6;font-family:'IBM Plex Mono',monospace">{critical_n}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:.25rem 0;
                        border-bottom:1px solid #0d1b2a;font-size:.8rem">
                <span style="color:#ffa726">● High</span>
                <span style="color:#e0eaf6;font-family:'IBM Plex Mono',monospace">{high_n}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:.25rem 0;
                        border-bottom:1px solid #0d1b2a;font-size:.8rem">
                <span style="color:#ffdd57">● Medium</span>
                <span style="color:#e0eaf6;font-family:'IBM Plex Mono',monospace">{int((ctx["risk_level"]=="Medium").sum())}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:.25rem 0;font-size:.8rem">
                <span style="color:#1de9b6">● Low</span>
                <span style="color:#e0eaf6;font-family:'IBM Plex Mono',monospace">{int((ctx["risk_level"]=="Low").sum())}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if top_pipe is not None:
        st.markdown(
            f"""
            <div class="cn-card" style="border-left:3px solid #ff3d3d">
                <div class="cn-card-title">Highest Risk Segment</div>
                <div style="font-family:'IBM Plex Mono',monospace;font-size:.9rem;
                            color:#ff3d3d;font-weight:600">{top_pipe['pipe_id']}</div>
                <div style="font-size:.75rem;color:#8faabf;margin-top:.3rem">
                    {top_pipe['material']} · {top_pipe['age']} yrs<br>
                    {top_pipe['ward']}<br>
                    Risk: <span style="color:#ff3d3d">{top_pipe['risk_score']:.1f}%</span><br>
                    Emergency: <span style="color:#ffa726">${top_pipe['emergency_cost']:,}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""
        <div class="cn-card">
            <div class="cn-card-title">Est. 12-mo Savings</div>
            <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.7rem;
                        font-weight:800;color:#1de9b6;line-height:1">
                ${ctx['expected_savings'].sum()/1_000_000:.1f}M
            </div>
            <div style="font-size:.68rem;color:#3d5a78;margin-top:.25rem">
                Proactive replacement vs emergency repair
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Data sources
    section_title("Data Sources")
    sources = [
        ("🔵", "Watermain Breaks", "Target variable"),
        ("🔵", "Watermains",       "Pipe characteristics"),
        ("🟢", "Street Trees",     "Root intrusion risk"),
        ("🟢", "Rain Gauges",      "Weather stress"),
        ("🟡", "311 Requests",     "Early warning"),
        ("🟡", "Utility Cuts",     "Construction disturbance"),
        ("🟠", "Lead Samples",     "Old pipe indicator"),
        ("🟠", "Road Resurfacing", "Age proxy"),
        ("🔴", "Building Permits", "Nearby activity"),
        ("🔴", "Neighbourhood",    "Age proxy"),
    ]
    for icon, name, role in sources:
        st.markdown(
            f"""
            <div style="display:flex;gap:.5rem;padding:.2rem 0;font-size:.72rem;
                        border-bottom:1px solid #07101f">
                <span>{icon}</span>
                <div>
                    <div style="color:#8faabf">{name}</div>
                    <div style="color:#3d5a78">{role}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
