"""Reusable UI widgets, custom CSS injections, and visual components for TalentCaspian."""

from typing import Any
import streamlit as st

from utils.auth import get_current_role, get_current_user, is_authenticated, logout_user_session


def render_custom_css() -> None:
    """Inject polished, modern custom CSS for dark/light responsive aesthetics."""
    st.markdown(
        """
        <style>
        /* Modern Glassmorphism & Clean Card Styling */
        .metric-container {
            background: linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.9) 100%);
            border: 1px solid rgba(51, 65, 85, 0.8);
            border-radius: 12px;
            padding: 16px 20px;
            margin-bottom: 12px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
            transition: transform 0.15s ease, border-color 0.15s ease;
        }
        .metric-container:hover {
            border-color: rgba(56, 189, 248, 0.6);
            transform: translateY(-2px);
        }
        .metric-title {
            color: #94A3B8;
            font-size: 0.85rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 4px;
        }
        .metric-value {
            color: #F8FAFC;
            font-size: 1.75rem;
            font-weight: 700;
            line-height: 1.2;
        }
        .metric-delta-positive {
            color: #10B981;
            font-size: 0.85rem;
            font-weight: 600;
            margin-top: 4px;
        }
        .metric-delta-neutral {
            color: #94A3B8;
            font-size: 0.85rem;
            margin-top: 4px;
        }
        
        /* Tag Chips */
        .tech-pill {
            display: inline-block;
            background: rgba(56, 189, 248, 0.12);
            color: #38BDF8;
            border: 1px solid rgba(56, 189, 248, 0.3);
            border-radius: 9999px;
            padding: 2px 10px;
            font-size: 0.75rem;
            font-weight: 500;
            margin-right: 6px;
            margin-bottom: 6px;
        }
        
        /* Status Badges */
        .badge-resolved {
            display: inline-block;
            background: rgba(16, 185, 129, 0.15);
            color: #34D399;
            border: 1px solid rgba(16, 185, 129, 0.4);
            border-radius: 6px;
            padding: 3px 8px;
            font-size: 0.75rem;
            font-weight: 600;
        }
        .badge-pending {
            display: inline-block;
            background: rgba(245, 158, 11, 0.15);
            color: #FBBF24;
            border: 1px solid rgba(245, 158, 11, 0.4);
            border-radius: 6px;
            padding: 3px 8px;
            font-size: 0.75rem;
            font-weight: 600;
        }
        
        /* Hero Badge */
        .hero-score-badge {
            background: linear-gradient(135deg, #0EA5E9 0%, #3B82F6 100%);
            color: #FFFFFF;
            border-radius: 8px;
            padding: 4px 12px;
            font-weight: 700;
            font-size: 1rem;
            display: inline-flex;
            align-items: center;
        }
        
        /* Callout Box */
        .ai-callout {
            background: rgba(15, 23, 42, 0.6);
            border-left: 4px solid #38BDF8;
            border-radius: 0 8px 8px 0;
            padding: 12px 16px;
            margin: 10px 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_navbar(current_page: str = "") -> None:
    """Render top brand header bar with authenticated user profile and navigation shortcuts.

    Args:
        current_page (str): Label of current active page.
    """
    col_brand, col_nav = st.columns([0.65, 0.35])

    with col_brand:
        st.markdown(
            """
            <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
                <span style="font-size: 28px;">⚡</span>
                <div>
                    <span style="font-size: 1.4rem; font-weight: 800; color: #F8FAFC; letter-spacing: -0.02em;">TalentCaspian</span>
                    <span style="font-size: 0.8rem; background: rgba(56,189,248,0.2); color: #38BDF8; padding: 2px 8px; border-radius: 6px; margin-left: 8px; font-weight: 600;">Autonomous Portfolio AI</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_nav:
        is_auth = is_authenticated()
        if is_auth:
            user = get_current_user() or {}
            role = get_current_role() or "user"
            name = user.get("name") or f"{role.capitalize()} #{user.get('id')}"

            c_info, c_btn = st.columns([0.65, 0.35])
            with c_info:
                st.markdown(
                    f"""
                    <div style="text-align: right; padding-top: 4px;">
                        <span style="font-size: 0.85rem; font-weight: 600; color: #F8FAFC;">{name}</span><br>
                        <span style="font-size: 0.72rem; color: #94A3B8; text-transform: uppercase;">{role}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with c_btn:
                if st.button("Logout", key=f"nav_logout_{current_page}", use_container_width=True):
                    logout_user_session()
                    st.toast("Logged out successfully.", icon="👋")
                    st.switch_page("pages/0_landing.py")
        else:
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Student Hub", key="nav_stu_login", use_container_width=True):
                    st.switch_page("pages/2_student_login.py")
            with c2:
                if st.button("Recruiter Hub", key="nav_rec_login", use_container_width=True):
                    st.switch_page("pages/5_recruiter_login.py")

    st.divider()


def render_score_badge(score: float | None) -> str:
    """Generate HTML badge string for a score.

    Args:
        score (float | None): Score value.

    Returns:
        str: HTML markup string.
    """
    if score is None:
        return '<span class="tech-pill" style="color: #94A3B8; border-color: #64748B;">Pending AI Scan</span>'

    val = float(score)
    if val >= 80:
        bg = "rgba(16, 185, 129, 0.2)"
        color = "#34D399"
        border = "rgba(16, 185, 129, 0.5)"
    elif val >= 60:
        bg = "rgba(56, 189, 248, 0.2)"
        color = "#38BDF8"
        border = "rgba(56, 189, 248, 0.5)"
    else:
        bg = "rgba(245, 158, 11, 0.2)"
        color = "#FBBF24"
        border = "rgba(245, 158, 11, 0.5)"

    return f'<span style="background:{bg}; color:{color}; border:1px solid {border}; border-radius:6px; padding:2px 8px; font-weight:700; font-size:0.85rem;">★ {val:.1f} / 100</span>'


def render_metric_card(
    label: str,
    value: Any,
    delta: str | None = None,
    help_text: str | None = None,
) -> None:
    """Render a styled metric card container.

    Args:
        label (str): Metric card title.
        value (Any): Metric main value.
        delta (str | None): Optional delta change indicator.
        help_text (str | None): Optional subtext/help description.
    """
    delta_html = ""
    if delta:
        cls = "metric-delta-positive" if delta.startswith("+") else "metric-delta-neutral"
        delta_html = f'<div class="{cls}">{delta}</div>'

    help_html = f'<div style="font-size:0.75rem; color:#64748B; margin-top:2px;">{help_text}</div>' if help_text else ""

    st.markdown(
        f"""
        <div class="metric-container">
            <div class="metric-title">{label}</div>
            <div class="metric-value">{value}</div>
            {delta_html}
            {help_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_tags(tags: list[str] | None) -> None:
    """Render a row of tag pill badges.

    Args:
        tags (list[str] | None): List of string tags.
    """
    if not tags:
        st.markdown('<span style="font-size:0.8rem; color:#64748B;">No tech tags detected</span>', unsafe_allow_html=True)
        return

    pills_html = "".join([f'<span class="tech-pill">#{t}</span>' for t in tags[:8]])
    st.markdown(f'<div style="margin-top: 4px; margin-bottom: 6px;">{pills_html}</div>', unsafe_allow_html=True)


def render_suggestion_card(suggestion: dict[str, Any], is_recruiter: bool = False) -> None:
    """Render a structured suggestion card with resolution status.

    Args:
        suggestion (dict[str, Any]): Suggestion record dict.
        is_recruiter (bool): Whether the view is rendered for a recruiter.
    """
    is_resolved = bool(suggestion.get("resolved"))
    status_badge = (
        '<span class="badge-resolved">✓ Resolved via GitHub push</span>'
        if is_resolved
        else '<span class="badge-pending">⏳ Open Action Required</span>'
    )

    rec_name = suggestion.get("recruiter_name") or f"Recruiter #{suggestion.get('recruiter_id', '')}"
    created_at = str(suggestion.get("created_at", ""))[:19]
    text = suggestion.get("suggestion_text", "")
    project_repo = suggestion.get("repo_url", "")

    header_text = f"Candidate Project: `{project_repo}`" if is_recruiter and project_repo else f"From **{rec_name}**"

    with st.container(border=True):
        col_hdr, col_badge = st.columns([0.65, 0.35])
        with col_hdr:
            st.markdown(f"**{header_text}** • <span style='font-size:0.75rem; color:#94A3B8;'>{created_at}</span>", unsafe_allow_html=True)
        with col_badge:
            st.markdown(f"<div style='text-align:right;'>{status_badge}</div>", unsafe_allow_html=True)

        st.markdown(f"> *\"{text}\"*")


def render_ai_next_steps(recommendations: list[dict[str, Any]] | list[str]) -> None:
    """Render Gemini AI next step suggestions.

    Args:
        recommendations (list[dict[str, Any]] | list[str]): Recommendation items.
    """
    if not recommendations:
        st.info("💡 Complete code scans and commit updates to generate AI next-step recommendations.")
        return

    for idx, item in enumerate(recommendations, 1):
        if isinstance(item, dict):
            title = item.get("title", f"Recommendation #{idx}")
            desc = item.get("description", "")
            impact = item.get("impact", "Medium Impact (+3-5 pts)")
            color = "#10B981" if "High" in impact else "#38BDF8"
            st.markdown(
                f"""
                <div class="ai-callout">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <strong style="color:#F8FAFC;">{idx}. {title}</strong>
                        <span style="font-size:0.75rem; color:{color}; font-weight:600;">{impact}</span>
                    </div>
                    <div style="font-size:0.85rem; color:#CBD5E1; margin-top:4px;">{desc}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
                <div class="ai-callout">
                    <strong style="color:#F8FAFC;">{idx}. Action Item</strong>
                    <div style="font-size:0.85rem; color:#CBD5E1; margin-top:2px;">{item}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
