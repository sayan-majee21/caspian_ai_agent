"""Student Registration Page for TalentCaspian."""

import streamlit as st

from utils.api_client import api_register_student
from utils.auth import login_user_session
from utils.ui_components import render_navbar

render_navbar("student_register")

st.markdown(
    """
    <div style="margin-bottom: 24px;">
        <h1 style="color: #F8FAFC; margin: 0; font-size: 1.8rem; font-weight: 800;">
            🎓 Student & Developer Registration
        </h1>
        <p style="color: #94A3B8; font-size: 0.95rem; margin-top: 4px;">
            Join TalentCaspian to showcase your engineering projects, obtain AI portfolio evaluation, and connect with top recruiters.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

col_form, col_info = st.columns([0.6, 0.4])

with col_form:
    with st.form("student_registration_form", clear_on_submit=False):
        name = st.text_input("Full Name *", placeholder="e.g. Alex Chen")
        email = st.text_input("Email Address *", placeholder="e.g. alex.chen@university.edu")
        github_username = st.text_input("GitHub Username *", placeholder="e.g. alexchen-dev")
        repo_url = st.text_input(
            "Initial Project Repository URL (Optional)",
            placeholder="https://github.com/username/project-repo",
            help="Providing a public repository will immediately enqueue background AI scanning with Gemini.",
        )

        submitted = st.form_submit_button("🚀 Create Account & Start AI Scan", type="primary", use_container_width=True)

        if submitted:
            if not name.strip() or not email.strip() or not github_username.strip():
                st.error("Please fill in all required fields (Name, Email, GitHub Username).")
            elif "@" not in email:
                st.error("Please provide a valid email address.")
            else:
                with st.spinner("Creating your student profile and initiating AI repository scanner..."):
                    try:
                        res = api_register_student(
                            name=name,
                            email=email,
                            github_username=github_username,
                            repo_url=repo_url if repo_url.strip() else None,
                        )
                        student_data = res.get("student", {})
                        token = f"stu_session_{student_data.get('id', 1)}"
                        login_user_session(student_data, "student", token)

                        st.success("🎉 Account created successfully! AI repository analysis is processing in the background.")
                        st.switch_page("pages/3_student_dashboard.py")
                    except Exception as exc:
                        st.error(f"Registration Failed: {exc}")

with col_info:
    with st.container(border=True):
        st.markdown("### 💡 Why Register?")
        st.markdown(
            """
            - **Instant Code Intelligence**: Gemini analyzes architecture, code depth, documentation, and test coverage.
            - **Recruiter Pipeline**: High-scoring projects automatically trigger notifications to matching hiring partners.
            - **Webhook Auto-Resolution**: When recruiters suggest changes, simply push commits to GitHub and our system validates them automatically.
            - **Personal Analytics**: Track score trajectories, peer ratings, and recruiter interest in one unified dashboard.
            """
        )
        st.divider()
        st.markdown("Already have a student account?")
        if st.button("Log In to Student Hub", use_container_width=True):
            st.switch_page("pages/2_student_login.py")
