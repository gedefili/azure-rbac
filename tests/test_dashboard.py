"""Tests for dashboard/app.py."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from azure_rbac.dashboard.app import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


SAMPLE_GRAPH = {
    "nodes": [
        {"id": "sub:001", "label": "Dev", "node_type": "resource",
         "sub_type": "subscription", "metadata": {}, "security_flags": []},
        {"id": "principal:u1", "label": "Alice", "node_type": "principal",
         "sub_type": "User", "metadata": {"principal_id": "u1"}, "security_flags": ["high:RBAC-001"]},
        {"id": "role:owner", "label": "Owner", "node_type": "role",
         "sub_type": "BuiltInRole", "metadata": {}, "security_flags": []},
    ],
    "links": [
        {"source": "principal:u1", "target": "role:owner",
         "edge_type": "assigned", "label": "assigned", "metadata": {}},
        {"source": "role:owner", "target": "sub:001",
         "edge_type": "scoped_to", "label": "scoped to", "metadata": {}},
    ],
}

SAMPLE_FINDINGS = [
    {
        "id": "RBAC-001-principal:u1-sub:001",
        "severity": "high",
        "title": "Owner at subscription scope",
        "description": "test",
        "affected_nodes": ["principal:u1"],
        "remediation": "fix",
        "references": [],
    },
    {
        "id": "RBAC-002-principal:u1",
        "severity": "medium",
        "title": "Direct user assignment",
        "description": "test",
        "affected_nodes": ["principal:u1"],
        "remediation": "use groups",
        "references": [],
    },
]


@pytest.fixture()
def app_with_data():
    """Create a Flask test app with graph and findings files on disk."""
    with tempfile.TemporaryDirectory() as tmpdir:
        graph_path = Path(tmpdir) / "graph.json"
        graph_path.write_text(json.dumps(SAMPLE_GRAPH))
        findings_path = Path(tmpdir) / "graph.findings.json"
        findings_path.write_text(json.dumps(SAMPLE_FINDINGS))

        flask_app = create_app(graph_path=str(graph_path))
        flask_app.config["TESTING"] = True
        yield flask_app


@pytest.fixture()
def app_empty():
    """Create a Flask test app with no data files."""
    flask_app = create_app(graph_path="/nonexistent/graph.json")
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture()
def client(app_with_data):
    return app_with_data.test_client()


@pytest.fixture()
def empty_client(app_empty):
    return app_empty.test_client()


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------


class TestSecurityHeaders:
    def test_csp_header_present(self, client):
        resp = client.get("/api/health")
        assert "Content-Security-Policy" in resp.headers

    def test_x_frame_options_deny(self, client):
        resp = client.get("/api/health")
        assert resp.headers["X-Frame-Options"] == "DENY"

    def test_x_content_type_options(self, client):
        resp = client.get("/api/health")
        assert resp.headers["X-Content-Type-Options"] == "nosniff"

    def test_referrer_policy(self, client):
        resp = client.get("/api/health")
        assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_permissions_policy(self, client):
        resp = client.get("/api/health")
        assert "geolocation=()" in resp.headers["Permissions-Policy"]

    def test_server_header_removed(self, client):
        resp = client.get("/api/health")
        assert "Server" not in resp.headers


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.get_json() == {"status": "healthy"}


# ---------------------------------------------------------------------------
# Index page
# ---------------------------------------------------------------------------


class TestIndexPage:
    def test_index_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"<!DOCTYPE html>" in resp.data or b"<html" in resp.data


# ---------------------------------------------------------------------------
# Graph endpoints
# ---------------------------------------------------------------------------


class TestGraphEndpoint:
    def test_returns_full_graph(self, client):
        resp = client.get("/api/graph")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "nodes" in data
        assert "links" in data
        assert len(data["nodes"]) == 3

    def test_filter_by_node_type(self, client):
        resp = client.get("/api/graph?node_type=principal")
        data = resp.get_json()
        assert all(n["node_type"] == "principal" for n in data["nodes"])

    def test_empty_graph_when_no_file(self, empty_client):
        resp = empty_client.get("/api/graph")
        data = resp.get_json()
        assert data == {"nodes": [], "links": []}


class TestNodeDetailEndpoint:
    def test_returns_node_and_neighbours(self, client):
        resp = client.get("/api/graph/node/principal:u1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["node"]["id"] == "principal:u1"
        assert len(data["neighbours"]) > 0
        assert len(data["links"]) > 0

    def test_not_found_returns_404(self, client):
        resp = client.get("/api/graph/node/nonexistent")
        assert resp.status_code == 404
        assert "error" in resp.get_json()


# ---------------------------------------------------------------------------
# Findings endpoints
# ---------------------------------------------------------------------------


class TestFindingsEndpoint:
    def test_returns_all_findings(self, client):
        resp = client.get("/api/findings")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 2

    def test_filter_by_severity(self, client):
        resp = client.get("/api/findings?severity=high")
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["severity"] == "high"

    def test_empty_findings_when_no_file(self, empty_client):
        resp = empty_client.get("/api/findings")
        data = resp.get_json()
        assert data == []


class TestFindingsSummaryEndpoint:
    def test_summary_counts(self, client):
        resp = client.get("/api/findings/summary")
        data = resp.get_json()
        assert data == {"high": 1, "medium": 1}

    def test_empty_summary(self, empty_client):
        resp = empty_client.get("/api/findings/summary")
        data = resp.get_json()
        assert data == {}


# ---------------------------------------------------------------------------
# Reload endpoint
# ---------------------------------------------------------------------------


class TestReloadEndpoint:
    def test_reload_without_token_env(self, client):
        resp = client.post("/api/graph/reload")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"

    def test_reload_with_valid_token(self, app_with_data):
        os.environ["RELOAD_TOKEN"] = "secret-token"
        try:
            test_client = app_with_data.test_client()
            resp = test_client.post(
                "/api/graph/reload",
                headers={"X-Reload-Token": "secret-token"},
            )
            assert resp.status_code == 200
        finally:
            os.environ.pop("RELOAD_TOKEN", None)

    def test_reload_with_invalid_token_returns_403(self, app_with_data):
        os.environ["RELOAD_TOKEN"] = "secret-token"
        try:
            test_client = app_with_data.test_client()
            resp = test_client.post(
                "/api/graph/reload",
                headers={"X-Reload-Token": "wrong-token"},
            )
            assert resp.status_code == 403
        finally:
            os.environ.pop("RELOAD_TOKEN", None)

    def test_reload_missing_token_returns_403(self, app_with_data):
        os.environ["RELOAD_TOKEN"] = "secret-token"
        try:
            test_client = app_with_data.test_client()
            resp = test_client.post("/api/graph/reload")
            assert resp.status_code == 403
        finally:
            os.environ.pop("RELOAD_TOKEN", None)


# ---------------------------------------------------------------------------
# CORS configuration
# ---------------------------------------------------------------------------


class TestCorsConfiguration:
    def test_cors_origins_from_env(self):
        os.environ["CORS_ORIGINS"] = "https://example.com"
        try:
            flask_app = create_app(graph_path="/nonexistent/graph.json")
            flask_app.config["TESTING"] = True
            test_client = flask_app.test_client()
            resp = test_client.get("/api/health")
            assert resp.status_code == 200
        finally:
            os.environ.pop("CORS_ORIGINS", None)
