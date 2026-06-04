"""
Task Module sub-package.

Provides fetch-payload builders and submit handlers for the two Task Module
dialogs: weekly report form and reporter-selection form.
"""

from src.adapters.teams.task_module.report_form import ReportFormModule
from src.adapters.teams.task_module.reporter_select_form import ReporterSelectFormModule

__all__ = ["ReportFormModule", "ReporterSelectFormModule"]
