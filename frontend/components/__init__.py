"""Shared UI components (re-exported for `from components import ...`)."""

from .anomalies import (
    build_anomalies_export_table,
    render_anomalies_section,
    render_anomaly_detection_settings_expander,
)
from .analysis import (
    build_year_options,
    filter_by_year_option,
    kpi_card,
    render_account_usage_charges_section,
    render_rate_compare_tab,
    render_schedule_compare_tab,
    render_usage_results_header,
)
from .ops import (
    render_ops_export_panel,
    render_ops_recalc_panel,
    render_ops_riders_panel,
    render_ops_tariff_panel,
    render_past_usage_bills_page,
    render_past_usage_results_page,
    render_recalc_results_like_upload,
)
from .tables import export_excel, export_excel_multi_sheet

__all__ = [
    "build_anomalies_export_table",
    "build_year_options",
    "export_excel",
    "export_excel_multi_sheet",
    "filter_by_year_option",
    "kpi_card",
    "render_account_usage_charges_section",
    "render_anomalies_section",
    "render_anomaly_detection_settings_expander",
    "render_ops_export_panel",
    "render_ops_recalc_panel",
    "render_ops_riders_panel",
    "render_ops_tariff_panel",
    "render_past_usage_bills_page",
    "render_past_usage_results_page",
    "render_rate_compare_tab",
    "render_recalc_results_like_upload",
    "render_schedule_compare_tab",
    "render_usage_results_header",
]
