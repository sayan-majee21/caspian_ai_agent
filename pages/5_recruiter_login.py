"""Recruiter Authentication & Login Page for TalentCaspian."""

import streamlit as st

from utils.api_client import api_login
from utils.auth import login_user_session
from utils.ui_components import render_navbar

render_navbar("recruiter_login")

st.markdown(
    """
    <div style="margin-bottom: 24px;">
        <h1 style="color: #F8FAFC; margin: 0; font-size: 1.8rem; font-weight: 800;">
            💼 Recruiter & Hiring Partner Login
        </h1>
        <p style="color: #94A3B8; font-size: 0.95rem; margin-top: 4px;">
            Access matched student candidates, track your suggestion history, and manage shortlists.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

col_form, col_quick = st.columns([0.6, 0.4])

with col_form:
    with st.form("recruiter_login_form"):
        email = st.text_input("Registered Work Email Address", placeholder="e.g. recruiter@company.com")
        submitted = st.form_submit_button("Sign In to Recruiter Workspace", type="primary", use_container_width=True)

        if submitted:
            if not email.strip():
                st.error("Please provide your work email address.")
            else:
                with st.spinner("Authenticating with TalentCaspian..."):
                    try:
                        res = api_login(email=email, user_type="recruiter")
                        user_data = res.get("user", {})
                        token = res.get("token", f"rec_session_{user_data.get('id', 1)}")
                        login_user_session(user_data, "recruiter", token)

                        st.toast(f"Welcome back, {user_data.get('name', 'Recruiter')}!", icon="🎉")
                        st.switch_page("pages/6_recruiter_dashboard.py")
                    except Exception as err:
                        st.error(f"Login failed: {err}")

    st.divider()
    st.markdown("New hiring partner? Register your filters:")
    if st.button("Create New Recruiter Account", use_container_width=True):
        st.switch_page("pages/4_recruiter_register.py")

with col_quick:
    with st.container(border=True):
        st.markdown("### ⚡ Quick Demo Recruiter Accounts")
        st.caption("Click any demo recruiter below to instantly explore matches:")

        demo_recruiters = [
            {"name": "Sarah Jenkins", "email": "sarah.jenkins@techcorp.com"},
            {"name": "DevRel Lead", "email": "devrel@startup.io"},
            {"name": "Hiring Partner", "email": "hiring@talenthub.ai"},
        ]

        for r in demo_recruiters:
            if st.button(f"🏢 {r['name']} ({r['email']})", key=f"quick_rec_{r['email']}", use_container_width=True):
                try:
                    res = api_login(email=r["email"], user_type="recruiter")
                    user_data = res.get("user", {})
                    token = res.get("token", f"rec_session_{user_data.get('id', 1)}")
                    login_user_session(user_data, "recruiter", token)
                    st.toast(f"Logged in as {r['name']}!", icon="🚀")
                    st.switch_page("pages/6_recruiter_dashboard.py")
                except Exception as e:
                    st.error(f"Could not log in as {r['name']}: {e}")
