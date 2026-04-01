"""
Integration tests: LangChain tools operating together on shared DataFrames.

All tests use purely in-memory DataFrames, no external services are mocked
because the tools themselves perform only pandas operations.
"""

import pytest
import pandas as pd

from src.tools.tools import get_tools


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_dfs():
    """Realistic two-file project-tracking dataset."""
    projects = pd.DataFrame(
        {
            "project_id": [1, 2, 3, 4, 5],
            "project_name": ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"],
            "status": ["Active", "On Hold", "Completed", "Active", "Cancelled"],
            "budget": [100_000, 200_000, 150_000, 120_000, 50_000],
            "risk_level": ["High", "Medium", "Low", "High", "Low"],
        }
    )
    tasks = pd.DataFrame(
        {
            "task_id": [101, 102, 103, 104, 105, 106],
            "project_id": [1, 1, 2, 3, 4, 4],
            "assignee": ["Alice", "Bob", "Alice", "Carol", "Bob", "Alice"],
            "status": ["Open", "Closed", "Open", "Closed", "Open", "Open"],
            "hours_estimate": [10, 5, 20, 8, 15, 12],
        }
    )
    return {"projects.csv": projects, "tasks.csv": tasks}


@pytest.fixture
def tools(project_dfs):
    return {t.name: t for t in get_tools(project_dfs)}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFilterWorkflow:
    def test_filter_workflow_summary_then_filter_high_risk(self, tools):
        """Simulate: summarise projects, then drill into High-risk ones."""
        summary = tools["get_data_summary"].invoke({"filename": "projects.csv"})
        assert "5" in summary  # sanity check

        filtered = tools["filter_rows"].invoke(
            {
                "filename": "projects.csv",
                "column_name": "risk_level",
                "operator": "==",
                "value": "High",
            }
        )
        assert "Alpha" in filtered
        assert "Delta" in filtered
        assert "Beta" not in filtered


class TestToolIsolation:
    def test_operations_on_one_df_do_not_affect_other(self, tools):
        """Tools should only see their own DataFrame's columns."""
        projects_summary = tools["get_data_summary"].invoke({"filename": "projects.csv"})
        tasks_summary = tools["get_data_summary"].invoke({"filename": "tasks.csv"})

        assert "project_name" in projects_summary
        assert "assignee" in tasks_summary
        # Cross-contamination checks
        assert "assignee" not in projects_summary
        assert "project_name" not in tasks_summary
