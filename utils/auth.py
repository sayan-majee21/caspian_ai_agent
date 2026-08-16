"""Authentication, session state, and cookie persistence utilities for TalentCaspian."""

import logging
from typing import Any

import streamlit as st

logger = logging.getLogger("talentcaspian.frontend.auth")

COOKIE_KEY_TOKEN = "tc_auth_token"
COOKIE_KEY_ROLE = "tc_user_type"
COOKIE_KEY_USER_ID = "tc_user_id"
COOKIE_KEY_NAME = "tc_user_name"
COOKIE_KEY_EMAIL = "tc_user_email"


def get_cookie_manager() -> Any | None:
    """Safely obtain or create the Extra-Streamlit-Components CookieManager.

    Returns:
        CookieManager instance or None if unavailable.
    """
    try:
        import extra_streamlit_components as stx

        if "_cookie_manager" not in st.session_state:
            st.session_state["_cookie_manager"] = stx.CookieManager(key="tc_cookies")
        return st.session_state["_cookie_manager"]
    except Exception as exc:
        logger.debug(f"CookieManager initialization fallback: {exc}")
        return None


def init_session_state() -> None:
    """Initialize default session state keys and rehydrate from cookies if present."""
    default_keys: dict[str, Any] = {
        "authenticated": False,
        "user_type": None,
        "user_id": None,
        "user_name": None,
        "user_email": None,
        "auth_token": None,
        "user_data": None,
    }

    for key, val in default_keys.items():
        if key not in st.session_state:
            st.session_state[key] = val

    # Attempt rehydration from cookies if not currently authenticated
    if not st.session_state.get("authenticated"):
        cookie_mgr = get_cookie_manager()
        if cookie_mgr:
            try:
                token = cookie_mgr.get(COOKIE_KEY_TOKEN)
                role = cookie_mgr.get(COOKIE_KEY_ROLE)
                uid_str = cookie_mgr.get(COOKIE_KEY_USER_ID)
                name = cookie_mgr.get(COOKIE_KEY_NAME)
                email = cookie_mgr.get(COOKIE_KEY_EMAIL)

                if token and role and uid_str:
                    st.session_state["authenticated"] = True
                    st.session_state["user_type"] = str(role)
                    st.session_state["user_id"] = int(uid_str)
                    st.session_state["user_name"] = str(name) if name else f"{role.capitalize()} #{uid_str}"
                    st.session_state["user_email"] = str(email) if email else ""
                    st.session_state["auth_token"] = str(token)
                    st.session_state["user_data"] = {
                        "id": int(uid_str),
                        "name": str(name) if name else "",
                        "email": str(email) if email else "",
                    }
            except Exception as exc:
                logger.debug(f"Cookie rehydration skipped: {exc}")


def login_user_session(user_data: dict[str, Any], user_type: str, token: str) -> None:
    """Store authenticated user profile in session state and persistent cookies.

    Args:
        user_data (dict[str, Any]): User record from backend login/registration.
        user_type (str): 'student' or 'recruiter'.
        token (str): Session token string.
    """
    user_id = user_data.get("id")
    name = user_data.get("name", f"User #{user_id}")
    email = user_data.get("email", "")

    st.session_state["authenticated"] = True
    st.session_state["user_type"] = user_type
    st.session_state["user_id"] = user_id
    st.session_state["user_name"] = name
    st.session_state["user_email"] = email
    st.session_state["auth_token"] = token
    st.session_state["user_data"] = user_data

    cookie_mgr = get_cookie_manager()
    if cookie_mgr:
        try:
            cookie_mgr.set(COOKIE_KEY_TOKEN, token, key="set_tok")
            cookie_mgr.set(COOKIE_KEY_ROLE, user_type, key="set_role")
            cookie_mgr.set(COOKIE_KEY_USER_ID, str(user_id), key="set_uid")
            cookie_mgr.set(COOKIE_KEY_NAME, name, key="set_name")
            cookie_mgr.set(COOKIE_KEY_EMAIL, email, key="set_email")
        except Exception as exc:
            logger.debug(f"Cookie write skipped: {exc}")


def logout_user_session() -> None:
    """Clear session state and remove authentication cookies."""
    st.session_state["authenticated"] = False
    st.session_state["user_type"] = None
    st.session_state["user_id"] = None
    st.session_state["user_name"] = None
    st.session_state["user_email"] = None
    st.session_state["auth_token"] = None
    st.session_state["user_data"] = None

    cookie_mgr = get_cookie_manager()
    if cookie_mgr:
        try:
            for key in [
                COOKIE_KEY_TOKEN,
                COOKIE_KEY_ROLE,
                COOKIE_KEY_USER_ID,
                COOKIE_KEY_NAME,
                COOKIE_KEY_EMAIL,
            ]:
                cookie_mgr.delete(key, key=f"del_{key}")
        except Exception as exc:
            logger.debug(f"Cookie deletion skipped: {exc}")


def is_authenticated() -> bool:
    """Check if a user session is active.

    Returns:
        bool: True if authenticated, False otherwise.
    """
    return bool(st.session_state.get("authenticated", False))


def get_current_user() -> dict[str, Any] | None:
    """Get the current authenticated user dictionary.

    Returns:
        dict[str, Any] | None: User object or None.
    """
    return st.session_state.get("user_data")


def get_current_role() -> str | None:
    """Get the current authenticated user role.

    Returns:
        str | None: 'student', 'recruiter', or None.
    """
    return st.session_state.get("user_type")


def require_role(allowed_role: str | list[str]) -> None:
    """Enforce role-based access guard on protected pages.

    Halts execution (`st.stop()`) and displays login prompt if authorization fails.

    Args:
        allowed_role (str | list[str]): Required role or list of acceptable roles.
    """
    init_session_state()

    allowed = [allowed_role] if isinstance(allowed_role, str) else allowed_role
    current_role = get_current_role()
    is_auth = is_authenticated()

    if not is_auth or current_role not in allowed:
        st.warning("🔒 **Authentication Required**")
        st.info(
            f"This page is protected and accessible exclusively to **{', '.join(r.capitalize() for r in allowed)}** accounts."
        )

        col1, col2, col3 = st.columns(3)
        with col1:
            if "student" in allowed and st.button("🎓 Go to Student Login", use_container_width=True):
                st.switch_page("pages/2_student_login.py")
        with col2:
            if "recruiter" in allowed and st.button("💼 Go to Recruiter Login", use_container_width=True):
                st.switch_page("pages/5_recruiter_login.py")
        with col3:
            if st.button("🏠 Return to Landing Page", use_container_width=True):
                st.switch_page("pages/0_landing.py")

        st.stop()
