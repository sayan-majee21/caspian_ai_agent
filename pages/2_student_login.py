"""Student Authentication & Login Page for TalentCaspian."""

import streamlit as st

from utils.api_client import api_login
from utils.auth import login_user_session
from utils.ui_components import render_navbar

render_navbar("student_login")

st.markdown(
    """
    <div style="margin-bottom: 24px;">
        <h1 style="color: #F8FAFC; margin: 0; font-size: 1.8rem; font-weight: 800;">
            🎓 Student & Developer Login
        </h1>
        <p style="color: #94A3B8; font-size: 0.95rem; margin-top: 4px;">
            Access your personal analytics, project portfolio, and recruiter feedback.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

col_form, col_quick = st.columns([0.6, 0.4])

with col_form:
    with st.form("student_login_form"):
        email = st.text_input("Registered Student Email Address", placeholder="e.g. krishna@example.com")
        submitted = st.form_submit_button("Sign In to Dashboard", type="primary", use_container_width=True)

        if submitted:
            if not email.strip():
                st.error("Please provide your registered email address.")
            else:
                with st.spinner("Authenticating with TalentCaspian..."):
                    try:
                        res = api_login(email=email, user_type="student")
                        user_data = res.get("user", {})
                        token = res.get("token", f"stu_session_{user_data.get('id', 1)}")
                        login_user_session(user_data, "student", token)

                        st.toast(f"Welcome back, {user_data.get('name', 'Developer')}!", icon="🎉")
                        st.switch_page("pages/3_student_dashboard.py")
                    except Exception as err:
                        st.error(f"Login failed: {err}")

    st.divider()
    st.markdown("New developer? Create your profile and scan your first repository:")
    if st.button("Create New Student Account", use_container_width=True):
        st.switch_page("pages/1_student_register.py")

with col_quick:
    with st.container(border=True):
        st.markdown("### ⚡ Quick Demo Accounts")
        st.caption("Click any demo user below to instantly log in without typing:")

        demo_users = [
            {"name": "Krishna Mahajan", "email": "krishna@example.com"},
            {"name": "Priya Sharma", "email": "priya@example.com"},
            {"name": "Rohan Gupta", "email": "rohan@example.com"},
            {"name": "Alex Chen", "email": "alex.chen@example.com"},
        ]

        for u in demo_users:
            if st.button(f"👤 {u['name']} ({u['email']})", key=f"quick_stu_{u['email']}", use_container_width=True):
                try:
                    res = api_login(email=u["email"], user_type="student")
                    user_data = res.get("user", {})
                    token = res.get("token", f"stu_session_{user_data.get('id', 1)}")
                    login_user_session(user_data, "student", token)
                    st.toast(f"Logged in as {u['name']}!", icon="🚀")
                    st.switch_page("pages/3_student_dashboard.py")
                except Exception as e:
                    st.error(f"Could not log in as {u['name']}: {e}")
