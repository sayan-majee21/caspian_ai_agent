"""Student Dashboard & Personal Analytics Workspace for TalentCaspian."""

import streamlit as st

from utils.api_client import (
    api_add_project,
    api_rate_project,
    api_submit_peer_suggestion,
    fetch_feed,
    fetch_project_analytics,
    fetch_project_commits,
    fetch_project_detail,
    fetch_project_ratings,
    fetch_project_suggestions,
    fetch_student_profile,
)
from utils.auth import get_current_user, require_role
from utils.charts import (
    create_commit_activity_chart,
    create_rating_timeline_chart,
    create_recruiter_demand_chart,
    create_score_breakdown_bars,
    create_score_gauge,
)
from utils.ui_components import (
    render_ai_next_steps,
    render_metric_card,
    render_navbar,
    render_score_badge,
    render_suggestion_card,
    render_tags,
)

# Enforce student authentication
require_role("student")
render_navbar("student_dashboard")

user = get_current_user() or {}
student_id = user.get("id", 1)

# Fetch student profile data
try:
    student_profile = fetch_student_profile(student_id)
    student_data = student_profile.get("student", {})
    projects = student_profile.get("projects", [])
    aggregate_stats = student_profile.get("aggregate_stats", {})
except Exception as e:
    st.error(f"Failed to load profile data: {e}")
    student_data = user
    projects = []
    aggregate_stats = {}

# Dashboard Header
st.markdown(
    f"""
    <div style="margin-bottom: 16px;">
        <h1 style="color: #F8FAFC; margin: 0; font-size: 1.8rem; font-weight: 800;">
            🎓 Developer Hub & Portfolio Workspace
        </h1>
        <p style="color: #94A3B8; font-size: 0.95rem; margin-top: 4px;">
            Welcome back, <b>{student_data.get('name', 'Developer')}</b> ({student_data.get('github_username', '')}). Track your code quality metrics and recruiter traction.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# 3 High-Impact Tabs
tab1, tab2, tab3 = st.tabs(["📊 Personal Analytics", "🌐 Community Feed & Peer Reviews", "➕ Add New Repository"])

# ==========================================
# TAB 1: PERSONAL ANALYTICS
# ==========================================
with tab1:
    if not projects:
        st.info("👋 You haven't added any projects to your portfolio yet. Head over to **'Add New Repository'** tab to connect your GitHub repo.")
    else:
        # Project Selector Bar
        proj_options = {p.get("id"): f"{p.get('repo_url', 'Project').split('/')[-1]} (Score: {p.get('final_score') or p.get('ai_score') or 'Pending'})" for p in projects}
        
        sel_c1, sel_c2 = st.columns([0.7, 0.3])
        with sel_c1:
            selected_proj_id = st.selectbox(
                "Select Portfolio Project for Deep Analytics:",
                options=list(proj_options.keys()),
                format_func=lambda x: proj_options[x],
            )
        with sel_c2:
            if st.button("🔄 Refresh Analysis Data", use_container_width=True):
                st.cache_data.clear()
                st.rerun()

        # Fetch detailed project analytics
        try:
            analytics = fetch_project_analytics(selected_proj_id)
        except Exception:
            analytics = {}

        # Extract analytics fields
        project_record = analytics.get("project") or next((p for p in projects if p.get("id") == selected_proj_id), {})
        header_info = analytics.get("header") or {}
        ai_score_hero = analytics.get("ai_score_hero") or {}
        breakdown_list = analytics.get("metric_breakdown") or [
            {"name": "Technical Quality (40%)", "score": project_record.get("ai_difficulty") or 0.0},
            {"name": "Code Authenticity (30%)", "score": project_record.get("ai_authenticity") or 0.0},
            {"name": "Project Creativity (30%)", "score": project_record.get("ai_creativity") or 0.0},
        ]
        commit_history = analytics.get("commits") or []
        recruiter_interest = analytics.get("recruiter_interest") or {}
        suggestions_list = analytics.get("recruiter_suggestions") or []
        ai_recommendations = analytics.get("ai_next_steps") or [
            {"title": "Expand Unit & Integration Testing", "description": "Add Pytest or Jest test suites with coverage >80% to boost Technical Quality score.", "impact": "High Impact (+5-8 pts)"},
            {"title": "Add Comprehensive API Documentation", "description": "Ensure OpenAPI / docstrings are fully annotated for all router endpoints.", "impact": "Medium Impact (+3-5 pts)"},
            {"title": "Set up CI/CD GitHub Actions", "description": "Automate linting and continuous testing workflows on push.", "impact": "Medium Impact (+3-4 pts)"},
        ]

        # 1. Project Header Banner
        repo_url = project_record.get("repo_url", "#")
        p_name = repo_url.split("/")[-1] if "/" in repo_url else f"Project #{selected_proj_id}"
        
        with st.container(border=True):
            h_col1, h_col2 = st.columns([0.7, 0.3])
            with h_col1:
                st.markdown(
                    f"""
                    <div style="font-size:1.3rem; font-weight:800; color:#F8FAFC;">
                        {p_name}
                    </div>
                    <div style="font-size:0.85rem; color:#38BDF8; margin-top:2px;">
                        <a href="{repo_url}" target="_blank" style="color:#38BDF8; text-decoration:none;">🔗 {repo_url}</a>
                    </div>
                    <p style="color:#94A3B8; font-size:0.9rem; margin-top:6px; margin-bottom:4px;">
                        {project_record.get('summary') or 'AI evaluation write-up generated by Gemini scanner.'}
                    </p>
                    """,
                    unsafe_allow_html=True,
                )
                render_tags(project_record.get("tags"))
            with h_col2:
                final_sc = project_record.get("final_score") or project_record.get("ai_score")
                st.markdown("<div style='text-align:right;'>", unsafe_allow_html=True)
                st.markdown(f"**Overall Rating:** {render_score_badge(final_sc)}", unsafe_allow_html=True)
                st.caption(f"Last Evaluation: {str(project_record.get('last_evaluated_at') or 'Live Sync')[:19]}")
                st.markdown("</div>", unsafe_allow_html=True)

        # 2. Score Breakdown & Hero Gauge
        sc_col1, sc_col2 = st.columns([0.45, 0.55])
        with sc_col1:
            score_val = ai_score_hero.get("final_score") or project_record.get("final_score") or project_record.get("ai_score") or 0.0
            fig_gauge = create_score_gauge(score_val, title="Composite AI Score", subtitle="Gemini Code Evaluation")
            st.plotly_chart(fig_gauge, use_container_width=True)
            
            delta_pts = ai_score_hero.get("score_delta", "+2.4 pts from peer community ratings")
            st.caption(f"📈 **Trajectory Signal:** {delta_pts}")

        with sc_col2:
            fig_breakdown = create_score_breakdown_bars(breakdown_list)
            st.plotly_chart(fig_breakdown, use_container_width=True)

        st.divider()

        # 3. Evolution & Ratings Timeline
        st.markdown("### 📈 Project Evolution & Rating Trajectory")
        tr_col1, tr_col2 = st.columns([0.6, 0.4])

        with tr_col1:
            ratings_data = fetch_project_ratings(selected_proj_id)
            ratings_list = ratings_data.get("ratings", [])
            fig_timeline = create_rating_timeline_chart(ratings_list)
            st.plotly_chart(fig_timeline, use_container_width=True)

        with tr_col2:
            commits_data = fetch_project_commits(selected_proj_id, limit=20)
            commits_list = commits_data.get("commits", commit_history)
            fig_commits = create_commit_activity_chart(commits_list)
            st.plotly_chart(fig_commits, use_container_width=True)

        # Recent Commits Log Table
        with st.expander("📜 View Recent Commits & Automated Change Classifications", expanded=False):
            if commits_list:
                for c in commits_list[:6]:
                    c_hash = c.get("commit_hash", "push")[:7]
                    c_msg = c.get("commit_message", "Repository commit")
                    c_class = c.get("change_classification", "minor")
                    c_badge = '<span class="badge-resolved">MAJOR</span>' if c_class == "major" else '<span class="tech-pill">MINOR</span>'
                    st.markdown(
                        f"""
                        <div style="display:flex; justify-content:space-between; align-items:center; padding: 4px 0; border-bottom: 1px solid rgba(51,65,85,0.4);">
                            <div>
                                <code style="color:#38BDF8;">{c_hash}</code> <span style="color:#CBD5E1; font-size:0.9rem;">{c_msg}</span>
                            </div>
                            <div>{c_badge}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("No GitHub commits recorded yet. Push new commits to trigger automated re-evaluation.")

        st.divider()

        # 4. Recruiter Signal & Feedback
        st.markdown("### 💼 Recruiter Interest & Actionable Feedback")
        rec_col1, rec_col2 = st.columns([0.4, 0.6])

        with rec_col1:
            match_count = recruiter_interest.get("matching_recruiter_count", 0)
            fig_rec = create_recruiter_demand_chart(match_count, total_pool=12)
            st.plotly_chart(fig_rec, use_container_width=True)
            st.caption(f"🎯 **{match_count} Tech Recruiters** currently have hiring filters matching this project's score and tech stack.")

        with rec_col2:
            st.markdown("**Recruiter Suggestions & Notes:**")
            if suggestions_list:
                for s in suggestions_list:
                    render_suggestion_card(s, is_recruiter=False)
            else:
                st.info("No recruiter suggestions received yet. As recruiters review your project, their improvement notes will appear here.")

        st.divider()

        # 5. AI Actionable Next Steps
        st.markdown("### 🤖 Gemini AI Next Steps (Recommended Actions)")
        render_ai_next_steps(ai_recommendations)


# ==========================================
# TAB 2: SEARCH & COMMUNITY FEED
# ==========================================
with tab2:
    st.markdown("### 🌐 Community Project Feed & Peer Review")
    st.caption("Discover work by fellow developers, submit constructive peer feedback, and rate projects.")

    feed_res = fetch_feed(page=1, limit=15)
    public_projects = feed_res.get("items", [])

    if not public_projects:
        st.info("No community projects available.")
    else:
        for p in public_projects:
            pid = p.get("id")
            pname = p.get("repo_url", "Project").split("/")[-1]
            pauthor = p.get("student_name") or p.get("author") or "Student"
            psummary = p.get("summary") or "AI evaluation pending..."
            pscore = p.get("final_score") or p.get("ai_score")

            with st.container(border=True):
                r1, r2 = st.columns([0.75, 0.25])
                with r1:
                    st.markdown(f"**{pname}** by `{pauthor}`")
                    st.caption(psummary)
                    render_tags(p.get("tags"))
                with r2:
                    st.markdown(f"<div style='text-align:right;'>{render_score_badge(pscore)}</div>", unsafe_allow_html=True)

                act_c1, act_c2 = st.columns(2)
                with act_c1:
                    if st.button(f"⭐ Rate #{pid}", key=f"stu_rate_feed_{pid}", use_container_width=True):
                        st.session_state[f"stu_show_rate_{pid}"] = True
                with act_c2:
                    if st.button(f"💬 Leave Peer Feedback #{pid}", key=f"stu_comment_feed_{pid}", use_container_width=True):
                        st.session_state[f"stu_show_comment_{pid}"] = True

                # Rate form
                if st.session_state.get(f"stu_show_rate_{pid}"):
                    with st.expander(f"Rate {pname} (1 to 10)", expanded=True):
                        s_rate = st.slider("Score", 1, 10, 8, key=f"stu_val_{pid}")
                        if st.button("Submit Rating", key=f"stu_sub_{pid}", type="primary"):
                            try:
                                api_rate_project(pid, s_rate, rater_type="public", rater_id=student_id)
                                st.success("Rating submitted!")
                                st.session_state[f"stu_show_rate_{pid}"] = False
                                st.rerun()
                            except Exception as err:
                                st.error(f"{err}")

                # Feedback form
                if st.session_state.get(f"stu_show_comment_{pid}"):
                    with st.expander(f"Leave Constructive Feedback for {pauthor}", expanded=True):
                        f_input = st.text_area("Your Feedback / Advice", key=f"stu_txt_{pid}", placeholder="Clean code! Consider breaking down long functions...")
                        if st.button("Post Peer Review", key=f"stu_post_{pid}", type="primary"):
                            if f_input.strip():
                                try:
                                    api_submit_peer_suggestion(
                                        project_id=pid,
                                        student_id=student_id,
                                        student_name=student_data.get("name", "Peer"),
                                        feedback_text=f_input,
                                    )
                                    st.success("Feedback posted successfully!")
                                    st.session_state[f"stu_show_comment_{pid}"] = False
                                    st.rerun()
                                except Exception as err:
                                    st.error(f"{err}")


# ==========================================
# TAB 3: ADD NEW PROJECT
# ==========================================
with tab3:
    st.markdown("### ➕ Connect an Additional GitHub Repository")
    st.caption("Submit a new public repository to be evaluated by Gemini Code Intelligence and added to your portfolio.")

    with st.form("add_project_form"):
        new_repo_url = st.text_input(
            "GitHub Repository URL *",
            placeholder="https://github.com/your-username/your-repository",
        )
        submit_add = st.form_submit_button("🚀 Scan & Add Repository", type="primary", use_container_width=True)

        if submit_add:
            if not new_repo_url.strip() or "github.com" not in new_repo_url:
                st.error("Please provide a valid GitHub repository URL.")
            else:
                with st.spinner("Submitting repository and launching background Gemini AI code evaluator..."):
                    try:
                        res = api_add_project(student_id=student_id, repo_url=new_repo_url.strip())
                        st.success("🎉 Project submitted! Gemini code scanner has been enqueued. Initial evaluation will complete shortly.")
                        st.rerun()
                    except Exception as err:
                        st.error(f"Failed to add project: {err}")
