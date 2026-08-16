"""Public Landing and Discovery Feed page for TalentCaspian."""

import streamlit as st

from utils.api_client import (
    api_add_to_cart,
    api_rate_project,
    api_submit_peer_suggestion,
    fetch_feed,
    fetch_project_detail,
)
from utils.auth import get_current_role, get_current_user, is_authenticated
from utils.ui_components import (
    render_metric_card,
    render_navbar,
    render_score_badge,
    render_tags,
)

render_navbar("landing")

# Hero Section
st.markdown(
    """
    <div style="background: linear-gradient(135deg, rgba(15, 23, 42, 0.9) 0%, rgba(30, 58, 138, 0.4) 100%); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 16px; padding: 32px; margin-bottom: 24px;">
        <h1 style="color: #F8FAFC; margin: 0; font-size: 2.2rem; font-weight: 800; letter-spacing: -0.02em;">
            Autonomous Tech Hiring & Portfolio Intelligence
        </h1>
        <p style="color: #94A3B8; font-size: 1.1rem; margin-top: 8px; margin-bottom: 20px; max-width: 800px;">
            TalentCaspian continuously scans GitHub repositories with Gemini Code Intelligence, scores technical depth, and autonomously matches verified candidates with recruiters in real time.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Key metric summary tiles
m1, m2, m3, m4 = st.columns(4)
with m1:
    render_metric_card("Evaluation Engine", "Gemini 2.5", delta="+Autonomous Scans", help_text="Multi-metric code analysis")
with m2:
    render_metric_card("Target Metric Bar", "Top 10%", delta="+Caspian Alerts", help_text="Filtered high-signal candidate pipeline")
with m3:
    render_metric_card("Webhooks", "Live Sync", delta="+Instant Rescores", help_text="Auto-resolves recruiter feedback on git push")
with m4:
    render_metric_card("Discovery Speed", "< 50ms", delta="+Instant Cache", help_text="Fast indexed search and filtering")

st.markdown("### 🔎 Live Discovery & Public Candidate Feed")

# Search and Filtering Controls
with st.container(border=True):
    col_search, col_tag, col_score, col_refresh = st.columns([0.4, 0.25, 0.25, 0.1])

    with col_search:
        search_query = st.text_input(
            "Keyword Search",
            placeholder="Search by student name, repo, or summary...",
            label_visibility="collapsed",
        )
    with col_tag:
        tag_filter = st.selectbox(
            "Filter by Technology",
            ["All Technologies", "fastapi", "react", "python", "postgresql", "docker", "machine-learning", "typescript", "fullstack"],
            label_visibility="collapsed",
        )
    with col_score:
        min_score = st.slider(
            "Min AI Score",
            min_value=0,
            max_value=100,
            value=0,
            step=5,
            label_visibility="collapsed",
            help="Filter by minimum AI score",
        )
    with col_refresh:
        if st.button("🔄 Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

clean_tag = None if tag_filter == "All Technologies" else tag_filter

# Fetch feed data
feed_data = fetch_feed(
    page=1,
    limit=20,
    search_query=search_query,
    tag=clean_tag,
    min_score=float(min_score) if min_score > 0 else None,
    preview=False,
)

items = feed_data.get("items", [])
total_count = feed_data.get("total", len(items))

st.caption(f"Showing **{len(items)}** of **{total_count}** evaluated projects matching your criteria.")

if not items:
    st.info("No projects found matching the filter criteria. Try resetting filters or lowering the score threshold.")
else:
    # Render candidate project cards
    for proj in items:
        p_id = proj.get("id")
        p_name = proj.get("repo_url", "Project").split("/")[-1] or f"Project #{p_id}"
        author = proj.get("student_name") or proj.get("author") or "Candidate"
        summary = proj.get("summary") or "AI repository evaluation underway..."
        final_score = proj.get("final_score") or proj.get("ai_score")
        tags = proj.get("tags") or []
        repo_url = proj.get("repo_url", "#")

        with st.container(border=True):
            c_header, c_score = st.columns([0.7, 0.3])
            with c_header:
                st.markdown(
                    f"""
                    <div style="font-size:1.15rem; font-weight:700; color:#F8FAFC;">
                        {p_name} <span style="font-size:0.85rem; font-weight:400; color:#94A3B8;">by <b>{author}</b></span>
                    </div>
                    <div style="font-size:0.8rem; color:#38BDF8; margin-top:2px;">
                        <a href="{repo_url}" target="_blank" style="color:#38BDF8; text-decoration:none;">🔗 {repo_url}</a>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with c_score:
                st.markdown(f"<div style='text-align:right;'>{render_score_badge(final_score)}</div>", unsafe_allow_html=True)

            st.markdown(f"<p style='color:#CBD5E1; font-size:0.9rem; margin-top:8px;'>{summary}</p>", unsafe_allow_html=True)
            render_tags(tags)

            # Interactive action row
            btn_col1, btn_col2, btn_col3 = st.columns([0.34, 0.33, 0.33])

            with btn_col1:
                if st.button(f"🔍 Deep View #{p_id}", key=f"feed_view_{p_id}", use_container_width=True):
                    st.session_state[f"show_modal_{p_id}"] = True

            with btn_col2:
                if st.button(f"⭐ Rate (1-10)", key=f"feed_rate_btn_{p_id}", use_container_width=True):
                    st.session_state[f"show_rate_{p_id}"] = True

            with btn_col3:
                role = get_current_role()
                if role == "recruiter":
                    if st.button(f"🛒 Add to Cart", key=f"feed_cart_{p_id}", use_container_width=True):
                        try:
                            user = get_current_user() or {}
                            api_add_to_cart(user.get("id", 1), p_id)
                            st.toast(f"Added {p_name} to your recruiter shortlist!", icon="🎉")
                        except Exception as e:
                            st.error(f"Error: {e}")
                else:
                    if st.button(f"💬 Feedback", key=f"feed_peer_btn_{p_id}", use_container_width=True):
                        st.session_state[f"show_peer_feed_{p_id}"] = True

            # Modal Dialog: Deep Project Details
            if st.session_state.get(f"show_modal_{p_id}"):
                with st.expander(f"📋 Detailed Breakdown for {p_name}", expanded=True):
                    try:
                        detail = fetch_project_detail(p_id)
                        p_obj = detail.get("project", {})
                        metrics = detail.get("metrics", [])
                        rec_interest = detail.get("recruiter_interest_count", 0)
                        peer_feedback = detail.get("peer_suggestions", [])

                        d_c1, d_c2, d_c3 = st.columns(3)
                        with d_c1:
                            st.metric("Technical Quality", f"{p_obj.get('ai_difficulty', 0):.1f} / 100")
                        with d_c2:
                            st.metric("Code Authenticity", f"{p_obj.get('ai_authenticity', 0):.1f} / 100")
                        with d_c3:
                            st.metric("Recruiter Demand", f"{rec_interest} Matches")

                        st.markdown("**Peer Community Feedback Thread:**")
                        if peer_feedback:
                            for pf in peer_feedback[:3]:
                                st.caption(f"💬 **{pf.get('student_name', 'Peer')}**: \"{pf.get('feedback_text')}\"")
                        else:
                            st.caption("No peer feedback comments yet. Be the first to provide feedback!")

                    except Exception as err:
                        st.error(f"Failed to fetch details: {err}")

                    if st.button("Close View", key=f"close_modal_{p_id}"):
                        st.session_state[f"show_modal_{p_id}"] = False
                        st.rerun()

            # Modal Dialog: Rate Project
            if st.session_state.get(f"show_rate_{p_id}"):
                with st.expander(f"⭐ Rate {p_name} (1 to 10)", expanded=True):
                    rate_val = st.slider("Select Score (10 is exceptional)", 1, 10, 8, key=f"rate_val_{p_id}")
                    if st.button("Submit Official Rating", key=f"rate_sub_{p_id}", type="primary"):
                        try:
                            user = get_current_user() or {}
                            role = get_current_role() or "public"
                            api_rate_project(
                                project_id=p_id,
                                rating=rate_val,
                                rater_type=role,
                                rater_id=user.get("id"),
                            )
                            st.success(f"Rating {rate_val}/10 recorded! Final score dynamically recalculated.")
                            st.session_state[f"show_rate_{p_id}"] = False
                            st.rerun()
                        except Exception as err:
                            st.error(f"{err}")

            # Modal Dialog: Submit Peer Feedback
            if st.session_state.get(f"show_peer_feed_{p_id}"):
                with st.expander(f"💬 Leave Peer Feedback on {p_name}", expanded=True):
                    user = get_current_user() or {}
                    d_name = st.text_input("Your Display Name", value=user.get("name", "Anonymous Peer"), key=f"peer_name_{p_id}")
                    f_text = st.text_area("Constructive Feedback / Suggestions", placeholder="Great project architecture! Consider adding unit tests for edge cases...", key=f"peer_text_{p_id}")
                    if st.button("Post Feedback", key=f"peer_post_{p_id}", type="primary"):
                        if f_text.strip():
                            try:
                                api_submit_peer_suggestion(
                                    project_id=p_id,
                                    student_id=user.get("id"),
                                    student_name=d_name,
                                    feedback_text=f_text,
                                )
                                st.success("Feedback posted successfully!")
                                st.session_state[f"show_peer_feed_{p_id}"] = False
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                        else:
                            st.warning("Please enter feedback text.")

# Footer Call to Action
st.divider()
cta_c1, cta_c2 = st.columns(2)
with cta_c1:
    with st.container(border=True):
        st.markdown("### 🎓 For Students & Developers")
        st.write("Connect your GitHub repository to get continuous AI code quality evaluation, recruiter visibility, and actionable recommendations.")
        if st.button("🚀 Register as Student", use_container_width=True, type="primary"):
            st.switch_page("pages/1_student_register.py")

with cta_c2:
    with st.container(border=True):
        st.markdown("### 🏢 For Tech Recruiters")
        st.write("Configure tech stack preferences and receive high-signal, verified candidate matches delivered directly to Telegram or email.")
        if st.button("💼 Register as Recruiter", use_container_width=True):
            st.switch_page("pages/4_recruiter_register.py")
