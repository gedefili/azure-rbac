"""Tests for graph_builder.py."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from azure_rbac.azure_client import (
    RoleAssignment,
    RoleDefinition,
    Subscription,
)
from azure_rbac.graph_builder import (
    EDGE_ASSIGNED,
    EDGE_SCOPED_TO,
    NODE_PRINCIPAL,
    NODE_RESOURCE,
    NODE_ROLE,
    GraphBuilder,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_client(
    subscriptions: list[Subscription] | None = None,
    role_assignments: list[RoleAssignment] | None = None,
    role_definitions: list[RoleDefinition] | None = None,
    resource_groups: list[dict] | None = None,
) -> MagicMock:
    client = MagicMock()
    client.list_subscriptions.return_value = subscriptions or []
    client.list_management_groups.return_value = []
    client.list_role_assignments.return_value = role_assignments or []
    client.list_role_definitions.return_value = role_definitions or []
    client.list_resource_groups.return_value = resource_groups or []
    return client


SAMPLE_SUB = Subscription(id="sub-001", display_name="My Subscription", state="Enabled")

SAMPLE_ROLE_DEF = RoleDefinition(
    id="/subscriptions/sub-001/providers/Microsoft.Authorization/roleDefinitions/owner-id",
    name="Owner",
    role_type="BuiltInRole",
    description="Full access",
    permissions=[{"actions": ["*"], "not_actions": [], "data_actions": [], "not_data_actions": []}],
)

SAMPLE_ASSIGNMENT = RoleAssignment(
    id="/subscriptions/sub-001/providers/Microsoft.Authorization/roleAssignments/ra-001",
    principal_id="user-aaa",
    principal_type="User",
    role_definition_id=SAMPLE_ROLE_DEF.id,
    scope="/subscriptions/sub-001",
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGraphBuilderBuild:
    def test_empty_tenant_produces_empty_graph(self):
        client = _make_client()
        builder = GraphBuilder(client)
        g = builder.build()
        assert g.number_of_nodes() == 0
        assert g.number_of_edges() == 0

    def test_subscription_node_created(self):
        client = _make_client(subscriptions=[SAMPLE_SUB])
        builder = GraphBuilder(client)
        builder.build()
        assert builder.graph.has_node("sub:sub-001")
        data = builder.graph.nodes["sub:sub-001"]
        assert data["node_type"] == NODE_RESOURCE
        assert data["sub_type"] == "subscription"
        assert data["label"] == "My Subscription"

    def test_role_assignment_creates_principal_role_and_edges(self):
        client = _make_client(
            subscriptions=[SAMPLE_SUB],
            role_definitions=[SAMPLE_ROLE_DEF],
            role_assignments=[SAMPLE_ASSIGNMENT],
        )
        builder = GraphBuilder(client)
        builder.build()
        g = builder.graph

        principal_id = "principal:user-aaa"
        role_id = f"role:{SAMPLE_ROLE_DEF.id}"

        assert g.has_node(principal_id), "Principal node should exist"
        assert g.nodes[principal_id]["node_type"] == NODE_PRINCIPAL
        assert g.nodes[principal_id]["sub_type"] == "User"

        assert g.has_node(role_id), "Role node should exist"
        assert g.nodes[role_id]["node_type"] == NODE_ROLE

        assert g.has_edge(principal_id, role_id), "assigned edge should exist"
        assert g.edges[principal_id, role_id]["edge_type"] == EDGE_ASSIGNED

        # Role should be scoped to subscription
        scope_id = "sub:sub-001"
        assert g.has_edge(role_id, scope_id), "scoped_to edge should exist"
        assert g.edges[role_id, scope_id]["edge_type"] == EDGE_SCOPED_TO

    def test_resource_group_node_created(self):
        client = _make_client(
            subscriptions=[SAMPLE_SUB],
            resource_groups=[{"name": "my-rg", "location": "eastus"}],
        )
        builder = GraphBuilder(client)
        builder.build()
        rg_id = "rg:sub-001:my-rg"
        assert builder.graph.has_node(rg_id)
        assert builder.graph.nodes[rg_id]["sub_type"] == "resource_group"

    def test_get_principals_returns_only_principals(self):
        client = _make_client(
            subscriptions=[SAMPLE_SUB],
            role_assignments=[SAMPLE_ASSIGNMENT],
        )
        builder = GraphBuilder(client)
        builder.build()
        principals = builder.get_principals()
        assert all(p["node_type"] == NODE_PRINCIPAL for p in principals)

    def test_get_resources_returns_only_resources(self):
        client = _make_client(subscriptions=[SAMPLE_SUB])
        builder = GraphBuilder(client)
        builder.build()
        resources = builder.get_resources()
        assert all(r["node_type"] == NODE_RESOURCE for r in resources)

    def test_get_role_assignments_for_principal(self):
        client = _make_client(
            subscriptions=[SAMPLE_SUB],
            role_definitions=[SAMPLE_ROLE_DEF],
            role_assignments=[SAMPLE_ASSIGNMENT],
        )
        builder = GraphBuilder(client)
        builder.build()
        assignments = builder.get_role_assignments_for_principal("principal:user-aaa")
        assert len(assignments) >= 1


class TestGraphBuilderSerialisation:
    def test_to_dict_structure(self):
        client = _make_client(subscriptions=[SAMPLE_SUB])
        builder = GraphBuilder(client)
        builder.build()
        d = builder.to_dict()
        assert "nodes" in d
        assert "links" in d
        assert isinstance(d["nodes"], list)
        assert isinstance(d["links"], list)

    def test_save_and_load_roundtrip(self):
        client = _make_client(
            subscriptions=[SAMPLE_SUB],
            role_definitions=[SAMPLE_ROLE_DEF],
            role_assignments=[SAMPLE_ASSIGNMENT],
        )
        builder = GraphBuilder(client)
        original_graph = builder.build()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "graph.json"
            builder.save(path)
            assert path.exists()

            loaded = GraphBuilder.load(path)
            assert loaded.graph.number_of_nodes() == original_graph.number_of_nodes()
            assert loaded.graph.number_of_edges() == original_graph.number_of_edges()

    def test_saved_json_is_valid(self):
        client = _make_client(subscriptions=[SAMPLE_SUB])
        builder = GraphBuilder(client)
        builder.build()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "graph.json"
            builder.save(path)
            data = json.loads(path.read_text())
            assert isinstance(data, dict)
            assert "nodes" in data

    def test_load_from_nonexistent_returns_empty(self):
        with pytest.raises(FileNotFoundError):
            GraphBuilder.load("/nonexistent/path/graph.json")


class TestGraphBuilderScopeResolution:
    def _build_with_scope(self, scope: str) -> GraphBuilder:
        assignment = RoleAssignment(
            id="ra-test",
            principal_id="princ-001",
            principal_type="User",
            role_definition_id=SAMPLE_ROLE_DEF.id,
            scope=scope,
        )
        client = _make_client(
            subscriptions=[SAMPLE_SUB],
            role_definitions=[SAMPLE_ROLE_DEF],
            role_assignments=[assignment],
        )
        builder = GraphBuilder(client)
        builder.build()
        return builder

    def test_subscription_scope_maps_to_sub_node(self):
        builder = self._build_with_scope("/subscriptions/sub-001")
        assert builder.graph.has_node("sub:sub-001")

    def test_resource_group_scope_maps_to_rg_node(self):
        builder = self._build_with_scope(
            "/subscriptions/sub-001/resourceGroups/my-rg"
        )
        assert builder.graph.has_node("rg:sub-001:my-rg")

    def test_generic_scope_creates_resource_node(self):
        scope = "/subscriptions/sub-001/resourceGroups/my-rg/providers/Microsoft.Storage/storageAccounts/mystorage"
        builder = self._build_with_scope(scope)
        # Should have some node for this scope
        assert builder.graph.number_of_nodes() > 0
