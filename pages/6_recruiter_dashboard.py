"""Recruiter Workspace & Candidate Discovery Dashboard for TalentCaspian."""

import streamlit as st

from utils.api_client import (
    api_add_to_cart,
    api_rate_project,
    api_remove_from_cart_by_item,
    api_submit_suggestion,
    api_update_recruiter_preferences,
    fetch_feed,
    fetch_recruiter_cart,
    fetch_recruiter_profile,
    fetch_recruiter_suggestions,
)
from utils.auth import get_current_user, require_role
from utils.ui_components import (
    render_navbar,
    render_score_badge,
    render_suggestion_card,
    render_tags,
)

# Enforce recruiter authentication
require_role("recruiter")
render_navbar("recruiter_dashboard")

user = get_current_user() or {}
recruiter_id = user.get("id", 1)

# Fetch recruiter profile & pre-matches
try:
    rec_profile_data = fetch_recruiter_profile(recruiter_id)
    recruiter_record = rec_profile_data.get("recruiter", user)
    matching_projects = rec_profile_data.get("matching_projects", [])
except Exception as err:
    st.error(f"Failed to load recruiter profile: {err}")
    recruiter_record = user
    matching_projects = []

# Recruiter Dashboard Header
standing_prefs = recruiter_record.get("preference_filters") or {}
standing_tags = standing_prefs.get("tech_stack") or ["fastapi", "python"]
standing_min_score = standing_prefs.get("min_score", 70)
channel_info = f"✈️ Telegram ({recruiter_record.get('telegram_handle')})" if recruiter_record.get("preferred_channel") == "telegram" else f"📩 Email ({recruiter_record.get('email')})"

st.markdown(
    f"""
    <div style="margin-bottom: 16px;">
        <h1 style="color: #F8FAFC; margin: 0; font-size: 1.8rem; font-weight: 800;">
            💼 Recruiter Discovery & Match Workspace
        </h1>
        <p style="color: #94A3B8; font-size: 0.95rem; margin-top: 4px;">
            Hiring Partner: <b>{recruiter_record.get('name', 'Recruiter')}</b> • Alert Route: <b>{channel_info}</b>
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Standing Preferences Banner
with st.container(border=True):
    col_b1, col_b2 = st.columns([0.7, 0.3])
    with col_b1:
        st.markdown(
            f"""
            <div style="font-size:0.85rem; color:#94A3B8; text-transform:uppercase; font-weight:600; letter-spacing:0.05em;">
                ⚡ Active Telegram & Email Notification Filter
            </div>
            <div style="font-size:1.05rem; font-weight:700; color:#F8FAFC; margin-top:4px;">
                Min AI Score: <span style="color:#38BDF8;">{standing_min_score}/100</span> • Target Stack: <span style="color:#10B981;">{', '.join(standing_tags) if standing_tags else 'Any'}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_b2:
        st.markdown(
            f"""
            <div style="text-align:right; font-size:0.85rem; color:#94A3B8; padding-top:6px;">
                Instant Caspian Bot Alerts: <span style="color:#10B981; font-weight:700;">ACTIVE</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

# 3 Operational Tabs
tab1, tab2, tab3 = st.tabs(["🎯 Matched Candidates & Discovery", "💬 Suggestion History & Replies", "🛒 Candidate Shortlist (Cart)"])

# ==========================================
# TAB 1: MATCHED CANDIDATES & DISCOVERY
# ==========================================
with tab1:
    st.markdown("### 🔎 Filter & Explore Candidate Projects")

    with st.container(border=True):
        f_col1, f_col2, f_col3 = st.columns([0.45, 0.35, 0.2])

        with f_col1:
            tech_options = ["fastapi", "react", "python", "postgresql", "docker", "machine-learning", "typescript", "node", "aws", "fullstack", "django", "vue", "golang"]
            safe_defaults = [t for t in standing_tags if t in tech_options] if isinstance(standing_tags, list) else ["python"]
            active_tech_filter = st.multiselect(
                "Filter by Tech Stack",
                options=tech_options,
                default=safe_defaults or ["python"],
                key="rec_tech_filter",
            )
        with f_col2:
            active_min_score = st.slider(
                "Minimum AI Quality Score",
                0,
                100,
                int(standing_min_score) if isinstance(standing_min_score, (int, float)) else 70,
                5,
                key="rec_score_filter",
            )
        with f_col3:
            st.markdown("<div style='padding-top:28px;'></div>", unsafe_allow_html=True)
            if st.button("💾 Save as Standing Filter", use_container_width=True, type="secondary"):
                try:
                    new_filters = {
                        "tech_stack": active_tech_filter,
                        "min_score": active_min_score,
                    }
                    api_update_recruiter_preferences(recruiter_id, new_filters)
                    st.toast("Hiring preferences updated in database & Caspian alert service!", icon="✅")
                    st.rerun()
                except Exception as err:
                    st.error(f"Failed to update preferences: {err}")

    # Fetch live feed matching the selected filters
    selected_tag = active_tech_filter[0] if active_tech_filter else None
    feed_data = fetch_feed(
        page=1,
        limit=25,
        tag=selected_tag,
        min_score=float(active_min_score),
    )
    candidates = feed_data.get("items", [])

    st.caption(f"Found **{len(candidates)}** matching candidates above score {active_min_score}.")

    if not candidates:
        st.info("No candidates match your current filter threshold. Try lowering the score slider or expanding tech stack tags.")
    else:
        for cand in candidates:
            c_id = cand.get("id")
            c_repo = cand.get("repo_url", "Project")
            c_name = c_repo.split("/")[-1] if "/" in c_repo else f"Project #{c_id}"
            c_author = cand.get("student_name") or cand.get("author") or "Candidate"
            c_summary = cand.get("summary") or "AI evaluation completed."
            c_score = cand.get("final_score") or cand.get("ai_score")
            c_tags = cand.get("tags") or []

            with st.container(border=True):
                r_head, r_score = st.columns([0.7, 0.3])
                with r_head:
                    st.markdown(f"#### {c_name} • <span style='font-size:0.95rem; font-weight:400; color:#94A3B8;'>Author: <b>{c_author}</b></span>", unsafe_allow_html=True)
                    st.markdown(f"<a href='{c_repo}' target='_blank' style='color:#38BDF8; font-size:0.85rem;'>🔗 View on GitHub: {c_repo}</a>", unsafe_allow_html=True)
                with r_score:
                    st.markdown(f"<div style='text-align:right;'>{render_score_badge(c_score)}</div>", unsafe_allow_html=True)

                st.markdown(f"<p style='color:#CBD5E1; font-size:0.9rem; margin-top:6px;'>{c_summary}</p>", unsafe_allow_html=True)
                render_tags(c_tags)

                act1, act2, act3 = st.columns(3)
                with act1:
                    if st.button(f"🛒 Add to Shortlist #{c_id}", key=f"cand_cart_{c_id}", use_container_width=True):
                        try:
                            api_add_to_cart(recruiter_id, c_id)
                            st.toast(f"Added {c_name} to your shortlist cart!", icon="🎉")
                        except Exception as e:
                            st.error(f"{e}")

                with act2:
                    if st.button(f"💬 Send Suggestion #{c_id}", key=f"cand_sugg_btn_{c_id}", use_container_width=True):
                        st.session_state[f"show_sugg_modal_{c_id}"] = True

                with act3:
                    if st.button(f"⭐ Recruiter Rating #{c_id}", key=f"cand_rate_btn_{c_id}", use_container_width=True):
                        st.session_state[f"show_rec_rate_{c_id}"] = True

                # Send Suggestion Expandable Box
                if st.session_state.get(f"show_sugg_modal_{c_id}"):
                    with st.expander(f"✉️ Send Improvement Suggestion to {c_author}", expanded=True):
                        st.caption("When the student pushes commits addressing this feedback, our GitHub webhook will automatically verify the fix and notify you.")
                        s_text = st.text_area(
                            "Constructive Suggestion",
                            placeholder="e.g., Consider adding rate limiting and automated Docker healthcheck scripts.",
                            key=f"sugg_text_{c_id}",
                        )
                        if st.button("Send Suggestion via Caspian", key=f"sub_sugg_{c_id}", type="primary"):
                            if s_text.strip():
                                try:
                                    api_submit_suggestion(
                                        project_id=c_id,
                                        recruiter_id=recruiter_id,
                                        suggestion_text=s_text,
                                    )
                                    st.success("Suggestion transmitted to student! Tracking on GitHub webhook listener.")
                                    st.session_state[f"show_sugg_modal_{c_id}"] = False
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"{e}")
                            else:
                                st.warning("Please enter suggestion text.")

                # Recruiter Rating Expandable Box
                if st.session_state.get(f"show_rec_rate_{c_id}"):
                    with st.expander(f"⭐ Rate Candidate {c_name} (Recruiter Evaluation)", expanded=True):
                        rec_rating = st.slider("Rating (1-10)", 1, 10, 9, key=f"rec_val_{c_id}")
                        if st.button("Submit Verified Rating", key=f"rec_sub_rate_{c_id}", type="primary"):
                            try:
                                api_rate_project(
                                    project_id=c_id,
                                    rating=rec_rating,
                                    rater_type="recruiter",
                                    rater_id=recruiter_id,
                                )
                                st.success("Recruiter rating recorded! Project composite score updated.")
                                st.session_state[f"show_rec_rate_{c_id}"] = False
                                st.rerun()
                            except Exception as err:
                                st.error(f"{err}")


# ==========================================
# TAB 2: SUGGESTION HISTORY & REPLIES
# ==========================================
with tab2:
    st.markdown("### 💬 Your Suggestion History & Live Status")
    st.caption("Track feedback you have sent to candidates. Once candidates push commits addressing your suggestions, status auto-updates to 'Resolved'.")

    c_ref1, c_ref2 = st.columns([0.8, 0.2])
    with c_ref2:
        if st.button("🔄 Sync Status", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    sugg_res = fetch_recruiter_suggestions(recruiter_id)
    sent_suggestions = sugg_res.get("suggestions", [])

    if not sent_suggestions:
        st.info("You haven't submitted any candidate suggestions yet. Click 'Send Suggestion' on any candidate card to propose improvements.")
    else:
        for s in sent_suggestions:
            render_suggestion_card(s, is_recruiter=True)


# ==========================================
# TAB 3: CANDIDATE SHORTLIST (CART)
# ==========================================
with tab3:
    st.markdown("### 🛒 Your Bookmarked Candidates Shortlist")
    st.caption("Manage wishlisted candidates for interviews and hiring outreach.")

    cart_res = fetch_recruiter_cart(recruiter_id)
    cart_items = cart_res.get("cart_items", [])

    if not cart_items:
        st.info("Your candidate shortlist cart is currently empty. Click 'Add to Shortlist' on candidate cards in Tab 1 to bookmark top talent.")
    else:
        st.write(f"Total Wishlisted: **{len(cart_items)}** candidates")

        for item in cart_items:
            item_id = item.get("id") or item.get("cart_item_id")
            p_id = item.get("project_id")
            proj_obj = item.get("project") or {}
            student_obj = proj_obj.get("student") or {}
            repo = proj_obj.get("repo_url") or item.get("repo_url") or f"Project #{p_id}"
            p_name = repo.rstrip("/").split("/")[-1] if "/" in repo else f"Project #{p_id}"
            author = student_obj.get("name") or item.get("student_name") or item.get("author") or "Student"
            score = proj_obj.get("final_score") or proj_obj.get("ai_score") or item.get("final_score") or item.get("ai_score")

            with st.container(border=True):
                c_c1, c_c2, c_c3 = st.columns([0.6, 0.25, 0.15])
                with c_c1:
                    st.markdown(f"**{p_name}** • Author: `{author}`")
                    st.markdown(f"<a href='{repo}' target='_blank' style='color:#38BDF8; font-size:0.85rem;'>🔗 {repo}</a>", unsafe_allow_html=True)
                with c_c2:
                    st.markdown(f"<div style='text-align:center;'>{render_score_badge(score)}</div>", unsafe_allow_html=True)
                with c_c3:
                    if st.button("🗑️ Remove", key=f"del_cart_{item_id}_{p_id}", use_container_width=True):
                        try:
                            if item_id:
                                api_remove_from_cart_by_item(item_id)
                            else:
                                from utils.api_client import api_remove_from_cart
                                api_remove_from_cart(recruiter_id, p_id)
                            st.toast(f"Removed {p_name} from cart.", icon="🗑️")
                            st.rerun()
                        except Exception as e:
                            st.error(f"{e}")
