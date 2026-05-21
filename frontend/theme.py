"""Theme CSS injection and palette helpers."""

from pathlib import Path

import streamlit as st

_STYLES = Path(__file__).resolve().parent / "styles"


def _read_style(name: str) -> str:
    return (_STYLES / name).read_text()


DARK_BASEWEB_CSS = _read_style("dark_baseweb.css")
LIGHT_BASEWEB_CSS = _read_style("light_baseweb.css")
GLOBAL_DARK_CSS = _read_style("dark_global.css")
LIGHT_OVERRIDE_CSS = _read_style("light_override.css")

def inject_baseweb_menu_css() -> None:
    """Event-container styles load after Streamlit emotion theme (fixes dark 'No results' panel)."""
    css = (
        LIGHT_BASEWEB_CSS
        if st.session_state.get("ui_theme") == "Light"
        else ""
    )
    st.html(f"<style id='tb-baseweb-menus'>{css}</style>")


def select_persisted_tab(labels: list[str], session_key: str) -> str:
    """Section picker that keeps the active tab across reruns (e.g. theme toggle)."""
    if session_key not in st.session_state or st.session_state[session_key] not in labels:
        st.session_state[session_key] = labels[0]
    selected = st.segmented_control(
        "Section",
        options=labels,
        default=st.session_state[session_key],
        key=session_key,
        label_visibility="collapsed",
        width="stretch",
    )
    return selected if selected is not None else st.session_state[session_key]


def theme_palette() -> dict:
    if st.session_state.get("ui_theme") == "Light":
        return {
            "chart_bg": "#faf8f5",
            "chart_stroke": "#d4ccc0",
            "axis_label": "#525252",
            "axis_title": "#111111",
            "grid": "#ded6cc",
            "usage_color": "#2563eb",
            "charge_color": "#475569",
            "table_bg": "#ffffff",
            "table_alt_bg": "#f7f3ed",
            "table_header_bg": "#e6ded2",
            "table_text": "#111111",
            "table_border": "#8f8578",
        }
    return {
        "chart_bg": "#0a0a0a",
        "chart_stroke": "#333333",
        "axis_label": "#a3a3a3",
        "axis_title": "#e5e5e5",
        "grid": "#333333",
        "usage_color": "#7cc7ff",
        "charge_color": "#9ca3af",
        "table_bg": "#0f131a",
        "table_alt_bg": "#111722",
        "table_header_bg": "#181b23",
        "table_text": "#f5f5f5",
        "table_border": "#333333",
    }



def apply_global_dark_styles() -> None:
    """Base dark theme (always loaded)."""
    st.markdown(f"<style>{GLOBAL_DARK_CSS}</style>", unsafe_allow_html=True)
    if st.session_state.get("ui_theme") == "Dark":
        st.markdown(
            f"<style id=\'tb-dark-baseweb-menus\'>{DARK_BASEWEB_CSS}</style>",
            unsafe_allow_html=True,
        )


def apply_light_override_styles() -> None:
    if st.session_state.get("ui_theme") == "Light":
        st.markdown(
            f"<style id=\'tb-app-theme-override\'>{LIGHT_OVERRIDE_CSS}</style>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown("<style id='tb-app-theme-override'></style>", unsafe_allow_html=True)


def finalize_theme() -> None:
    """Tail inject for portaled Baseweb menus (event container)."""
    inject_baseweb_menu_css()


def init_theme_state() -> None:
    """Session defaults for theme toggle."""
    if "ui_theme" not in st.session_state:
        st.session_state["ui_theme"] = "Dark"
