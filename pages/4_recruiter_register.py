"""Recruiter Registration Page for TalentCaspian."""

import streamlit as st

from utils.api_client import api_register_recruiter
from utils.auth import login_user_session
from utils.ui_components import render_navbar

render_navbar("recruiter_register")

st.markdown(
    """
    <div style="margin-bottom: 24px;">
        <h1 style="color: #F8FAFC; margin: 0; font-size: 1.8rem; font-weight: 800;">
            🏢 Recruiter & Hiring Partner Registration
        </h1>
        <p style="color: #94A3B8; font-size: 0.95rem; margin-top: 4px;">
            Set your target tech stack filters and receive high-signal, AI-verified candidate alerts via Telegram or Email.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

col_form, col_info = st.columns([0.6, 0.4])

with col_form:
    with st.form("recruiter_registration_form"):
        name = st.text_input("Recruiter / Company Name *", placeholder="e.g. Sarah Jenkins (Acme Corp)")
        email = st.text_input("Work Email Address *", placeholder="e.g. sarah@acmecorp.com")

        channel = st.selectbox(
            "Preferred Instant Alert Channel *",
            options=["email", "telegram"],
            format_func=lambda x: "📩 Email Notifications" if x == "email" else "✈️ Telegram Bot Alerts (Real-Time)",
        )

        telegram_handle = st.text_input(
            "Telegram Handle (Required if Telegram is selected)",
            placeholder="@sarah_recruiter",
            help="Caspian Listener agent will dispatch instant alerts to this handle when matching candidates are evaluated.",
        )

        st.markdown("##### 🎯 Hiring Filters & Criteria")
        tech_tags = st.multiselect(
            "Target Tech Stack & Domains",
            options=["fastapi", "react", "python", "postgresql", "docker", "machine-learning", "typescript", "node", "aws"],
            default=["python", "fastapi"],
        )

        min_score = st.slider("Minimum AI Quality Score (0 - 100)", 0, 100, 75, step=5)

        submitted = st.form_submit_button("🚀 Register & Activate Smart Matcher", type="primary", use_container_width=True)

        if submitted:
            if not name.strip() or not email.strip():
                st.error("Please fill in all required fields (Name, Email).")
            elif channel == "telegram" and not telegram_handle.strip():
                st.error("Telegram Handle is required when Telegram Bot alerts are chosen.")
            else:
                with st.spinner("Setting up recruiter matching pipeline..."):
                    try:
                        pref_filters = {
                            "tech_stack": tech_tags,
                            "min_score": min_score,
                        }
                        rec_res = api_register_recruiter(
                            name=name,
                            email=email,
                            preferred_channel=channel,
                            telegram_handle=telegram_handle if channel == "telegram" else None,
                            preference_filters=pref_filters,
                        )
                        token = f"rec_session_{rec_res.get('id', 1)}"
                        login_user_session(rec_res, "recruiter", token)

                        st.success("🎉 Recruiter profile created! Redirecting to your candidate match workspace...")
                        st.switch_page("pages/6_recruiter_dashboard.py")
                    except Exception as exc:
                        st.error(f"Registration Failed: {exc}")

with col_info:
    with st.container(border=True):
        st.markdown("### ⚡ Why Recruit with TalentCaspian?")
        st.markdown(
            """
            - **No Resume Fluff**: Code is evaluated directly on GitHub using Gemini Code Intelligence for authenticity and depth.
            - **Instant Telegram Alerts**: Receive candidate cards the minute high-scoring projects match your tech filters.
            - **Two-Way Suggestion Loop**: Suggest improvements to candidates directly; get notified when they push code fixing your comments.
            - **Shortlist Wishlist (Cart)**: Bookmark top candidates into a unified workspace.
            """
        )
        st.divider()
        st.markdown("Already registered as a recruiter?")
        if st.button("Log In to Recruiter Hub", use_container_width=True):
            st.switch_page("pages/5_recruiter_login.py")
