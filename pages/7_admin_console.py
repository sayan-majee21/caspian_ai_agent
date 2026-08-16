"""Admin & Developer Testing Console for TalentCaspian."""

import json
import uuid
import httpx
import streamlit as st

from utils.api_client import (
    api_admin_notify,
    api_admin_scan,
    api_trigger_webhook,
    clear_api_cache,
    get_admin_api_key,
    get_backend_url,
)
from utils.ui_components import render_metric_card, render_navbar

render_navbar("admin_console")

st.markdown(
    """
    <div style="margin-bottom: 24px;">
        <h1 style="color: #F8FAFC; margin: 0; font-size: 1.8rem; font-weight: 800;">
            🛠️ Admin & Developer Diagnostic Console
        </h1>
        <p style="color: #94A3B8; font-size: 0.95rem; margin-top: 4px;">
            Hackathon control center: Trigger AI repository evaluations, simulate Caspian Telegram recruiter dispatches, and test GitHub push webhooks.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Live Backend Health Ping
backend_url = get_backend_url()
is_healthy = False
health_latency = 0.0

try:
    with httpx.Client(timeout=3.0) as client:
        resp = client.get(f"{backend_url}/docs")
        is_healthy = resp.status_code == 200
except Exception:
    is_healthy = False

h1, h2, h3 = st.columns(3)
with h1:
    status_label = "🟢 ONLINE" if is_healthy else "🔴 OFFLINE / UNREACHABLE"
    render_metric_card("Backend API Server", status_label, help_text=backend_url)
with h2:
    render_metric_card("Admin Key Config", "Configured", help_text=f"Default: {get_admin_api_key()[:6]}...")
with h3:
    if st.button("🧹 Flush All Frontend Caches", use_container_width=True):
        clear_api_cache()
        st.toast("Frontend caches cleared!", icon="✨")

st.divider()

col_tools1, col_tools2 = st.columns(2)

# ==========================================
# TOOL 1: TRIGGER AI SCANNER
# ==========================================
with col_tools1:
    with st.container(border=True):
        st.markdown("### 🤖 Agent 1: Trigger AI Repository Scan")
        st.caption("Enqueues asynchronous Gemini evaluation for a specific project or all pending projects.")

        with st.form("admin_scan_form"):
            scan_proj_id = st.number_input("Target Project ID (0 for all projects)", min_value=0, value=1, step=1)
            admin_key_input = st.text_input("Admin API Key", value=get_admin_api_key(), type="password")

            sub_scan = st.form_submit_button("🚀 Enqueue AI Scan Task", type="primary", use_container_width=True)

            if sub_scan:
                try:
                    pid = int(scan_proj_id) if scan_proj_id > 0 else None
                    res = api_admin_scan(project_id=pid, admin_key=admin_key_input)
                    st.success(f"Task Queued: {res.get('message', 'AI scanning queued')}")
                    st.json(res)
                except Exception as err:
                    st.error(f"Scan trigger failed: {err}")

# ==========================================
# TOOL 2: TRIGGER RECRUITER NOTIFICATIONS
# ==========================================
with col_tools2:
    with st.container(border=True):
        st.markdown("### ✈️ Agent 2: Trigger Caspian Telegram Alerts")
        st.caption("Matches candidate projects against active recruiter filters and dispatches multi-channel alerts.")

        with st.form("admin_notify_form"):
            notify_proj_id = st.number_input("Project ID to Notify For", min_value=1, value=1, step=1)
            notify_rec_id = st.number_input("Optional Specific Recruiter ID (0 for all matching)", min_value=0, value=0, step=1)
            notify_admin_key = st.text_input("Admin API Key", value=get_admin_api_key(), type="password", key="notify_key")

            sub_notify = st.form_submit_button("📢 Dispatch Recruiter Alerts", type="primary", use_container_width=True)

            if sub_notify:
                try:
                    rid = int(notify_rec_id) if notify_rec_id > 0 else None
                    res = api_admin_notify(project_id=int(notify_proj_id), recruiter_id=rid, admin_key=notify_admin_key)
                    st.success("Notification task queued for Caspian worker dispatch!")
                    st.json(res)
                except Exception as err:
                    st.error(f"Notification dispatch failed: {err}")

st.divider()

# ==========================================
# TOOL 3: GITHUB WEBHOOK SIMULATOR
# ==========================================
st.markdown("### 🔄 GitHub Webhook Simulator (Commit Push & Auto-Resolution)")
st.caption("Simulate real-time GitHub push payloads to test change classification, incremental re-scoring, and recruiter suggestion resolution.")

with st.container(border=True):
    sim_col1, sim_col2 = st.columns([0.5, 0.5])

    with sim_col1:
        repo_input = st.text_input("Target GitHub Repo URL", value="https://github.com/alexchen-dev/fastapi-caspian-demo")
        commit_msg = st.text_input("Commit Message", value="feat: add rate limiting and security headers per recruiter suggestion")
        modified_files = st.text_area("Modified Files (one per line)", value="routers/public.py\nservices/gemini_scanner.py\nREADME.md")

    with sim_col2:
        delivery_uuid = str(uuid.uuid4())
        files_list = [f.strip() for f in modified_files.split("\n") if f.strip()]
        commit_id = uuid.uuid4().hex[:12]

        simulated_payload = {
            "repository": {
                "html_url": repo_input.strip(),
                "full_name": repo_input.replace("https://github.com/", "").strip(),
            },
            "commits": [
                {
                    "id": commit_id,
                    "message": commit_msg.strip(),
                    "added": [],
                    "removed": [],
                    "modified": files_list,
                }
            ],
            "head_commit": {
                "id": commit_id,
                "message": commit_msg.strip(),
            },
        }

        st.markdown("**Simulated Payload Preview:**")
        st.code(json.dumps(simulated_payload, indent=2), language="json")

        if st.button("⚡ Dispatch Simulated GitHub Webhook Event", type="primary", use_container_width=True):
            try:
                res = api_trigger_webhook(
                    payload=simulated_payload,
                    event="push",
                    delivery_id=delivery_uuid,
                    secret="skip_signature_verification",
                )
                st.success(f"Webhook Accepted: {res.get('message', 'Processed successfully')}")
                st.toast("GitHub push event processed! Incremental evaluation enqueued.", icon="🎉")
            except Exception as err:
                st.error(f"Webhook simulation failed: {err}")
