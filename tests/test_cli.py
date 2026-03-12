"""Tests for cli.py."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from azure_rbac.cli import _setup_logging, app

runner = CliRunner()


# ---------------------------------------------------------------------------
# _setup_logging
# ---------------------------------------------------------------------------


class TestSetupLogging:
    def test_verbose_sets_debug(self):
        # Reset handlers so basicConfig can re-apply
        logging.root.handlers.clear()
        _setup_logging(verbose=True)
        assert logging.root.level == logging.DEBUG

    def test_non_verbose_sets_info(self):
        logging.root.handlers.clear()
        _setup_logging(verbose=False)
        assert logging.root.level == logging.INFO


# ---------------------------------------------------------------------------
# build command
# ---------------------------------------------------------------------------


class TestBuildCommand:
    @patch("azure_rbac.cli.console")
    def test_build_writes_graph_json(self, mock_console):
        mock_client = MagicMock()
        mock_client.list_subscriptions.return_value = []
        mock_client.list_management_groups.return_value = []

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "graph.json"
            with (
                patch("azure_rbac.azure_client.SubscriptionClient"),
                patch("azure_rbac.azure_client.DefaultAzureCredential"),
                patch("azure_rbac.graph_builder.AzureClient", return_value=mock_client),
            ):
                result = runner.invoke(app, ["build", "--output", str(output_path)])

            assert result.exit_code == 0, result.output
            assert output_path.exists()
            data = json.loads(output_path.read_text())
            assert "nodes" in data
            assert "links" in data


# ---------------------------------------------------------------------------
# analyze command
# ---------------------------------------------------------------------------


class TestAnalyzeCommand:
    @patch("azure_rbac.cli.console")
    def test_analyze_reads_graph_and_prints_table(self, mock_console):
        graph_data = {
            "nodes": [
                {"id": "sub:001", "label": "Dev", "node_type": "resource",
                 "sub_type": "subscription", "metadata": {}, "security_flags": []},
            ],
            "links": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            graph_path = Path(tmpdir) / "graph.json"
            graph_path.write_text(json.dumps(graph_data))
            result = runner.invoke(app, ["analyze", "--graph", str(graph_path)])

        assert result.exit_code == 0, result.output

    @patch("azure_rbac.cli.console")
    def test_analyze_missing_graph_exits_1(self, mock_console):
        result = runner.invoke(app, ["analyze", "--graph", "/nonexistent/graph.json"])
        assert result.exit_code == 1

    @patch("azure_rbac.cli.console")
    def test_analyze_writes_findings_to_output(self, mock_console):
        graph_data = {
            "nodes": [
                {"id": "principal:u1", "label": "u1", "node_type": "principal",
                 "sub_type": "User", "metadata": {"principal_id": "u1"}, "security_flags": []},
                {"id": "role:r1", "label": "Owner", "node_type": "role",
                 "sub_type": "BuiltInRole", "metadata": {"permissions": []}, "security_flags": []},
                {"id": "sub:001", "label": "Dev", "node_type": "resource",
                 "sub_type": "subscription", "metadata": {}, "security_flags": []},
            ],
            "links": [
                {"source": "principal:u1", "target": "role:r1",
                 "edge_type": "assigned", "label": "assigned", "metadata": {}},
                {"source": "role:r1", "target": "sub:001",
                 "edge_type": "scoped_to", "label": "scoped to", "metadata": {}},
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            graph_path = Path(tmpdir) / "graph.json"
            graph_path.write_text(json.dumps(graph_data))
            out_path = Path(tmpdir) / "findings.json"
            result = runner.invoke(
                app, ["analyze", "--graph", str(graph_path), "--output", str(out_path)]
            )
            assert result.exit_code == 0, result.output
            assert out_path.exists()
            findings = json.loads(out_path.read_text())
            assert isinstance(findings, list)


# ---------------------------------------------------------------------------
# advise command
# ---------------------------------------------------------------------------


class TestAdviseCommand:
    @patch("azure_rbac.cli.console")
    def test_advise_missing_findings_exits_1(self, mock_console):
        result = runner.invoke(app, ["advise", "--findings", "/nonexistent/findings.json"])
        assert result.exit_code == 1

    @patch("azure_rbac.cli.console")
    def test_advise_calls_ai_advisor(self, mock_console):
        findings_data = [
            {
                "id": "RBAC-001-principal:u1-sub:001",
                "severity": "high",
                "title": "Privileged role at subscription scope",
                "description": "test",
                "affected_nodes": [],
                "remediation": "fix it",
                "references": [],
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            findings_path = Path(tmpdir) / "findings.json"
            findings_path.write_text(json.dumps(findings_data))

            mock_advisor = MagicMock()
            mock_advisor.generate_remediation_report.return_value = "# Report\nAll good."

            with patch("azure_rbac.ai_advisor.AIAdvisor", return_value=mock_advisor):
                result = runner.invoke(app, ["advise", "--findings", str(findings_path)])

        assert result.exit_code == 0, result.output

    @patch("azure_rbac.cli.console")
    def test_advise_with_graph_option(self, mock_console):
        findings_data = [
            {
                "id": "RBAC-001-test",
                "severity": "high",
                "title": "Test finding",
                "description": "test",
                "affected_nodes": [],
                "remediation": "fix",
                "references": [],
            }
        ]
        graph_data = {
            "nodes": [
                {"id": "sub:001", "label": "Dev", "node_type": "resource",
                 "sub_type": "subscription", "metadata": {}, "security_flags": []}
            ],
            "links": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            findings_path = Path(tmpdir) / "findings.json"
            findings_path.write_text(json.dumps(findings_data))
            graph_path = Path(tmpdir) / "graph.json"
            graph_path.write_text(json.dumps(graph_data))

            mock_advisor = MagicMock()
            mock_advisor.generate_remediation_report.return_value = "# Report"

            with patch("azure_rbac.ai_advisor.AIAdvisor", return_value=mock_advisor):
                result = runner.invoke(
                    app,
                    ["advise", "--findings", str(findings_path), "--graph", str(graph_path)],
                )

        assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# dashboard command
# ---------------------------------------------------------------------------


class TestDashboardCommand:
    @patch("azure_rbac.cli.console")
    def test_dashboard_calls_flask_run(self, mock_console):
        mock_flask_app = MagicMock()
        with patch("azure_rbac.dashboard.app.create_app", return_value=mock_flask_app):
            result = runner.invoke(app, ["dashboard", "--port", "5001"])

        assert result.exit_code == 0, result.output
        mock_flask_app.run.assert_called_once()
