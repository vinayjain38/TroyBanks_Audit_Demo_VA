"""Operations pages: tariff, riders, past usage."""

import streamlit as st

from components import (
    render_ops_riders_panel,
    render_ops_tariff_panel,
    render_past_usage_bills_page,
    render_past_usage_results_page,
)


def render_tariff() -> None:
    render_ops_tariff_panel()


def render_riders() -> None:
    render_ops_riders_panel()


def render_past_usage() -> None:
    render_past_usage_bills_page()


def render_past_usage_results() -> None:
    render_past_usage_results_page()
