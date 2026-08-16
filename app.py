"""TalentCaspian — Autonomous AI Hiring & Portfolio Intelligence Streamlit Frontend.

Entry point initializing page configuration, theme, and navigation.
"""

import streamlit as st

from utils.auth import get_current_role, get_current_user, init_session_state, is_authenticated, logout_user_session
from utils.ui_components import render_custom_css

# Configure wide responsive layout
st.set_page_config(
    page_title="TalentCaspian — AI Portfolio & Tech Hiring",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Rehydrate session state & cookies
init_session_state()
render_custom_css()

# Define navigation pages
landing_page = st.Page("pages/0_landing.py", title="Public Discovery", icon="🌐", default=True)
stu_reg_page = st.Page("pages/1_student_register.py", title="Student Registration", icon="📝")
stu_login_page = st.Page("pages/2_student_login.py", title="Student Login", icon="🎓")
stu_dash_page = st.Page("pages/3_student_dashboard.py", title="Student Dashboard", icon="📊")

rec_reg_page = st.Page("pages/4_recruiter_register.py", title="Recruiter Registration", icon="🏢")
rec_login_page = st.Page("pages/5_recruiter_login.py", title="Recruiter Login", icon="💼")
rec_dash_page = st.Page("pages/6_recruiter_dashboard.py", title="Recruiter Dashboard", icon="🎯")

admin_page = st.Page("pages/7_admin_console.py", title="Admin & Dev Console", icon="🛠️")

# Build navigation hierarchy based on session role
pages_dict = {
    "Discovery & Auth": [
        landing_page,
        stu_login_page,
        stu_reg_page,
        rec_login_page,
        rec_reg_page,
    ],
    "Student Hub": [
        stu_dash_page,
    ],
    "Recruiter Hub": [
        rec_dash_page,
    ],
    "Developer Tools": [
        admin_page,
    ],
}

nav = st.navigation(pages_dict)

# Sidebar identity pill
with st.sidebar:
    st.markdown(
        """
        <div style="padding: 10px 0;">
            <h2 style="margin:0; font-size:1.4rem; color:#F8FAFC;">⚡ TalentCaspian</h2>
            <p style="margin:0; font-size:0.78rem; color:#38BDF8; font-weight:600;">Autonomous Agentic Hiring</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.divider()

    if is_authenticated():
        user = get_current_user() or {}
        role = get_current_role() or "user"
        st.success(f"Logged in as **{user.get('name', 'User')}**")
        st.caption(f"Role: **{role.upper()}** • ID #{user.get('id')}")

        if st.button("🚪 Log Out", use_container_width=True):
            logout_user_session()
            st.toast("Logged out.", icon="👋")
            st.rerun()
    else:
        st.info("💡 Log in to submit ratings, access Personal Analytics, or shortlist candidates.")

    st.divider()
    st.caption("TalentCaspian v1.0 • Powered by Caspian & Gemini 2.5 Pro")

# Run active page
nav.run()
