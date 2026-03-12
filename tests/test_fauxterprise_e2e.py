"""End-to-end test that exercises the full azure-rbac tool against Fauxterprise.

Simulates the real workflow a user would follow:

  1. Generate the fixture from Terraform
  2. Build the RBAC graph   (``azure-rbac build --fixture``)
  3. Save the graph to JSON
  4. Reload the graph from JSON
  5. Run security analysis   (``azure-rbac analyze``)
  6. Write findings to JSON
  7. Serve the dashboard and hit every API endpoint (``azure-rbac dashboard``)

No Azure credentials or external services are required.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

FAUX_ROOT = Path(__file__).resolve().parent.parent / "fauxterprise"


# ---------------------------------------------------------------------------
# Fixture: generate once, share across tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def _ensure_faux_on_path() -> None:
    if str(FAUX_ROOT) not in sys.path:
        sys.path.insert(0, str(FAUX_ROOT))


@pytest.fixture(scope="module")
def fixture_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from generate_fixture import generate_fixture
    data = generate_fixture(FAUX_ROOT)
    path = tmp_path_factory.mktemp("e2e") / "fixture.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def built_graph(fixture_path: Path, tmp_path_factory: pytest.TempPathFactory):
    """Build graph via MockAzureClient → GraphBuilder (mirrors ``azure-rbac build -f``)."""
    from azure_rbac.graph_builder import GraphBuilder
    from azure_rbac.mock_client import MockAzureClient

    client = MockAzureClient(fixture_path)
    builder = GraphBuilder(client)
    graph = builder.build()

    graph_path = tmp_path_factory.mktemp("e2e") / "graph.json"
    builder.save(graph_path)
    return builder, graph, graph_path


@pytest.fixture(scope="module")
def findings(built_graph):
    """Run security analysis (mirrors ``azure-rbac analyze``)."""
    from azure_rbac.security_analyzer import SecurityAnalyzer

    builder, graph, _ = built_graph
    analyzer = SecurityAnalyzer(graph)
    return analyzer.analyze()


@pytest.fixture(scope="module")
def findings_path(findings, built_graph, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Persist findings to JSON (mirrors ``azure-rbac analyze -o``)."""
    _, _, graph_path = built_graph
    fpath = graph_path.with_suffix("").with_suffix(".findings.json")
    data = [f.to_dict() for f in findings]
    fpath.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return fpath


@pytest.fixture(scope="module")
def dashboard_client(built_graph, findings_path):
    """Create a Flask test client serving the real graph + findings."""
    from azure_rbac.dashboard.app import create_app

    _, _, graph_path = built_graph
    app = create_app(graph_path=str(graph_path))
    app.config["TESTING"] = True
    return app.test_client()


# ═══════════════════════════════════════════════════════════════════════════
# 1. Build graph
# ═══════════════════════════════════════════════════════════════════════════


class TestBuildGraph:
    """``azure-rbac build --fixture`` simulation."""

    def test_graph_has_nodes(self, built_graph) -> None:
        _, graph, _ = built_graph
        assert graph.number_of_nodes() > 100

    def test_graph_has_edges(self, built_graph) -> None:
        _, graph, _ = built_graph
        assert graph.number_of_edges() > 100

    def test_graph_has_subscriptions(self, built_graph) -> None:
        _, graph, _ = built_graph
        sub_nodes = [n for n, d in graph.nodes(data=True) if d.get("sub_type") == "subscription"]
        assert len(sub_nodes) == 10

    def test_graph_has_management_groups(self, built_graph) -> None:
        _, graph, _ = built_graph
        mg_nodes = [n for n, d in graph.nodes(data=True) if d.get("sub_type") == "management_group"]
        assert len(mg_nodes) == 11

    def test_graph_has_principals(self, built_graph) -> None:
        builder, _, _ = built_graph
        principals = builder.get_principals()
        assert len(principals) > 10

    def test_graph_has_resources(self, built_graph) -> None:
        builder, _, _ = built_graph
        resources = builder.get_resources()
        assert len(resources) > 20

    def test_graph_has_role_nodes(self, built_graph) -> None:
        _, graph, _ = built_graph
        role_nodes = [n for n, d in graph.nodes(data=True) if d.get("node_type") == "role"]
        assert len(role_nodes) > 5

    def test_graph_saved_to_disk(self, built_graph) -> None:
        _, _, graph_path = built_graph
        assert graph_path.exists()
        assert graph_path.stat().st_size > 1000

    def test_graph_json_structure(self, built_graph) -> None:
        _, _, graph_path = built_graph
        data = json.loads(graph_path.read_text(encoding="utf-8"))
        assert "nodes" in data
        assert "links" in data
        assert len(data["nodes"]) > 100
        assert len(data["links"]) > 100

    def test_graph_reload_roundtrip(self, built_graph) -> None:
        from azure_rbac.graph_builder import GraphBuilder

        _, graph, graph_path = built_graph
        reloaded = GraphBuilder.load(graph_path)
        assert reloaded.graph.number_of_nodes() == graph.number_of_nodes()
        assert reloaded.graph.number_of_edges() == graph.number_of_edges()


# ═══════════════════════════════════════════════════════════════════════════
# 2. Security analysis
# ═══════════════════════════════════════════════════════════════════════════


class TestSecurityAnalysis:
    """``azure-rbac analyze`` simulation."""

    def test_findings_non_empty(self, findings) -> None:
        assert len(findings) > 0

    def test_findings_have_severities(self, findings) -> None:
        severities = {f.severity.value for f in findings}
        assert len(severities) >= 1

    def test_direct_or_orphaned_findings_detected(self, findings) -> None:
        """Fauxterprise scopes to RGs, so RBAC-002/003 should fire."""
        prefixes = {f.id.split("-")[0] + "-" + f.id.split("-")[1] for f in findings}
        assert "RBAC-002" in prefixes or "RBAC-003" in prefixes, (
            f"Expected RBAC-002 or RBAC-003 findings, got: {prefixes}"
        )

    def test_direct_user_assignments_detected(self, findings) -> None:
        """Users 10-14 have direct Contributor → should flag RBAC-002."""
        rbac002 = [f for f in findings if f.id.startswith("RBAC-002")]
        assert len(rbac002) > 0, "Expected direct user assignment findings"

    def test_findings_have_affected_nodes(self, findings) -> None:
        for f in findings:
            if f.id.startswith("RBAC-006"):
                continue  # group adoption is graph-wide, no specific nodes
            assert f.affected_nodes or f.description, (
                f"Finding {f.id} has no affected_nodes and no description"
            )

    def test_findings_serialise_to_json(self, findings) -> None:
        data = [f.to_dict() for f in findings]
        text = json.dumps(data)
        assert len(text) > 100
        reloaded = json.loads(text)
        assert len(reloaded) == len(findings)

    def test_findings_written_to_disk(self, findings_path) -> None:
        assert findings_path.exists()
        data = json.loads(findings_path.read_text(encoding="utf-8"))
        assert len(data) > 0


# ═══════════════════════════════════════════════════════════════════════════
# 3. Dashboard serving the real Fauxterprise graph
# ═══════════════════════════════════════════════════════════════════════════


class TestDashboard:
    """``azure-rbac dashboard`` simulation – exercises every API endpoint."""

    def test_health(self, dashboard_client) -> None:
        resp = dashboard_client.get("/api/health")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "healthy"

    def test_index_page(self, dashboard_client) -> None:
        resp = dashboard_client.get("/")
        assert resp.status_code == 200
        assert b"<html" in resp.data or b"<!DOCTYPE" in resp.data

    def test_graph_api_returns_full_graph(self, dashboard_client, built_graph) -> None:
        _, graph, _ = built_graph
        resp = dashboard_client.get("/api/graph")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["nodes"]) == graph.number_of_nodes()
        assert len(data["links"]) == graph.number_of_edges()

    def test_graph_filter_by_principal(self, dashboard_client) -> None:
        resp = dashboard_client.get("/api/graph?node_type=principal")
        assert resp.status_code == 200
        data = resp.get_json()
        assert all(n["node_type"] == "principal" for n in data["nodes"])
        assert len(data["nodes"]) > 0

    def test_graph_filter_by_resource(self, dashboard_client) -> None:
        resp = dashboard_client.get("/api/graph?node_type=resource")
        assert resp.status_code == 200
        data = resp.get_json()
        assert all(n["node_type"] == "resource" for n in data["nodes"])
        assert len(data["nodes"]) > 0

    def test_graph_filter_by_role(self, dashboard_client) -> None:
        resp = dashboard_client.get("/api/graph?node_type=role")
        assert resp.status_code == 200
        data = resp.get_json()
        assert all(n["node_type"] == "role" for n in data["nodes"])
        assert len(data["nodes"]) > 0

    def test_node_detail_endpoint(self, dashboard_client) -> None:
        # Get a real node id from the graph
        resp = dashboard_client.get("/api/graph?node_type=principal")
        data = resp.get_json()
        assert len(data["nodes"]) > 0
        node_id = data["nodes"][0]["id"]

        resp = dashboard_client.get(f"/api/graph/node/{node_id}")
        assert resp.status_code == 200
        detail = resp.get_json()
        assert detail["node"]["id"] == node_id
        assert "neighbours" in detail
        assert "links" in detail

    def test_node_detail_404(self, dashboard_client) -> None:
        resp = dashboard_client.get("/api/graph/node/nonexistent-node")
        assert resp.status_code == 404

    def test_findings_api(self, dashboard_client) -> None:
        resp = dashboard_client.get("/api/findings")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) > 0

    def test_findings_filter_by_severity(self, dashboard_client) -> None:
        # First get all findings to find a severity that exists
        resp = dashboard_client.get("/api/findings")
        all_findings = resp.get_json()
        if all_findings:
            sev = all_findings[0]["severity"]
            resp = dashboard_client.get(f"/api/findings?severity={sev}")
            data = resp.get_json()
            assert all(f["severity"] == sev for f in data)

    def test_findings_summary(self, dashboard_client) -> None:
        resp = dashboard_client.get("/api/findings/summary")
        assert resp.status_code == 200
        summary = resp.get_json()
        assert isinstance(summary, dict)
        assert sum(summary.values()) > 0

    def test_reload_endpoint(self, dashboard_client) -> None:
        resp = dashboard_client.post("/api/graph/reload")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"

    def test_security_headers_on_real_graph(self, dashboard_client) -> None:
        resp = dashboard_client.get("/api/graph")
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert "Content-Security-Policy" in resp.headers


# ═══════════════════════════════════════════════════════════════════════════
# 4. CLI entry-point smoke (build command with --fixture)
# ═══════════════════════════════════════════════════════════════════════════


class TestCLISmoke:
    """Verify the Typer CLI ``build`` command works with a fixture."""

    def test_build_command_creates_graph(self, fixture_path, tmp_path) -> None:
        from typer.testing import CliRunner
        from azure_rbac.cli import app

        output = tmp_path / "cli-graph.json"
        runner = CliRunner()
        result = runner.invoke(app, ["build", "-f", str(fixture_path), "-o", str(output)])
        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert output.exists()
        data = json.loads(output.read_text(encoding="utf-8"))
        assert len(data["nodes"]) > 100

    def test_analyze_command_prints_table(self, built_graph) -> None:
        from typer.testing import CliRunner
        from azure_rbac.cli import app

        _, _, graph_path = built_graph
        runner = CliRunner()
        result = runner.invoke(app, ["analyze", "-g", str(graph_path)])
        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert "Security Findings" in result.output or "RBAC" in result.output

    def test_analyze_command_writes_findings(self, built_graph, tmp_path) -> None:
        from typer.testing import CliRunner
        from azure_rbac.cli import app

        _, _, graph_path = built_graph
        output = tmp_path / "cli-findings.json"
        runner = CliRunner()
        result = runner.invoke(app, ["analyze", "-g", str(graph_path), "-o", str(output)])
        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert output.exists()
        findings = json.loads(output.read_text(encoding="utf-8"))
        assert len(findings) > 0
