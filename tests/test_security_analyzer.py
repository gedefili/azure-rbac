"""Tests for security_analyzer.py."""

from __future__ import annotations

import networkx as nx
import pytest

from azure_rbac.security_analyzer import Finding, SecurityAnalyzer, Severity


# ---------------------------------------------------------------------------
# Graph construction helpers
# ---------------------------------------------------------------------------


def _make_graph() -> nx.DiGraph:
    return nx.DiGraph()


def _add_principal(g: nx.DiGraph, pid: str, sub_type: str = "User", label: str | None = None) -> None:
    g.add_node(
        pid,
        label=label or pid,
        node_type="principal",
        sub_type=sub_type,
        metadata={"principal_id": pid},
        security_flags=[],
    )


def _add_role(
    g: nx.DiGraph, rid: str, label: str = "Owner", role_type: str = "BuiltInRole",
    permissions: list | None = None,
) -> None:
    g.add_node(
        rid,
        label=label,
        node_type="role",
        sub_type=role_type,
        metadata={"permissions": permissions or []},
        security_flags=[],
    )


def _add_resource(g: nx.DiGraph, rid: str, sub_type: str = "subscription", label: str = "My Sub") -> None:
    g.add_node(
        rid,
        label=label,
        node_type="resource",
        sub_type=sub_type,
        metadata={},
        security_flags=[],
    )


def _assign(g: nx.DiGraph, principal: str, role: str, scope: str) -> None:
    """Add principal --[assigned]--> role --[scoped_to]--> scope edges."""
    g.add_edge(principal, role, edge_type="assigned", label="assigned", metadata={})
    g.add_edge(role, scope, edge_type="scoped_to", label="scoped to", metadata={})


# ---------------------------------------------------------------------------
# RBAC-001: Privileged role at subscription scope
# ---------------------------------------------------------------------------


class TestOwnerAtSubscription:
    def test_owner_at_subscription_detected(self):
        g = _make_graph()
        _add_principal(g, "principal:alice", "User", "alice@contoso.com")
        _add_role(g, "role:owner", "Owner", "BuiltInRole")
        _add_resource(g, "sub:001", "subscription")
        _assign(g, "principal:alice", "role:owner", "sub:001")

        findings = SecurityAnalyzer(g).analyze()
        rbac001 = [f for f in findings if f.id.startswith("RBAC-001")]
        assert len(rbac001) >= 1
        assert rbac001[0].severity == Severity.HIGH

    def test_contributor_at_subscription_detected(self):
        g = _make_graph()
        _add_principal(g, "principal:bob", "User")
        _add_role(g, "role:contributor", "Contributor", "BuiltInRole")
        _add_resource(g, "sub:002", "subscription")
        _assign(g, "principal:bob", "role:contributor", "sub:002")

        findings = SecurityAnalyzer(g).analyze()
        rbac001 = [f for f in findings if f.id.startswith("RBAC-001")]
        assert len(rbac001) >= 1

    def test_reader_at_subscription_not_flagged(self):
        g = _make_graph()
        _add_principal(g, "principal:carol", "User")
        _add_role(g, "role:reader", "Reader", "BuiltInRole")
        _add_resource(g, "sub:003", "subscription")
        _assign(g, "principal:carol", "role:reader", "sub:003")

        findings = SecurityAnalyzer(g).analyze()
        rbac001 = [f for f in findings if f.id.startswith("RBAC-001")]
        assert len(rbac001) == 0

    def test_owner_at_resource_group_not_flagged_as_subscription(self):
        g = _make_graph()
        _add_principal(g, "principal:dave", "User")
        _add_role(g, "role:owner2", "Owner", "BuiltInRole")
        # resource group node – not a subscription
        _add_resource(g, "rg:001:my-rg", "resource_group")
        _assign(g, "principal:dave", "role:owner2", "rg:001:my-rg")

        findings = SecurityAnalyzer(g).analyze()
        rbac001 = [f for f in findings if f.id.startswith("RBAC-001")]
        assert len(rbac001) == 0


# ---------------------------------------------------------------------------
# RBAC-002: Direct user assignment
# ---------------------------------------------------------------------------


class TestDirectUserAssignment:
    def test_direct_user_detected(self):
        g = _make_graph()
        _add_principal(g, "principal:eve", "User")
        _add_role(g, "role:reader", "Reader")
        _add_resource(g, "sub:001", "subscription")
        _assign(g, "principal:eve", "role:reader", "sub:001")

        findings = SecurityAnalyzer(g).analyze()
        rbac002 = [f for f in findings if f.id.startswith("RBAC-002")]
        assert len(rbac002) == 1
        assert rbac002[0].severity == Severity.MEDIUM

    def test_group_assignment_not_flagged(self):
        g = _make_graph()
        _add_principal(g, "principal:devteam", "Group")
        _add_role(g, "role:reader", "Reader")
        _add_resource(g, "sub:001", "subscription")
        _assign(g, "principal:devteam", "role:reader", "sub:001")

        findings = SecurityAnalyzer(g).analyze()
        rbac002 = [f for f in findings if f.id.startswith("RBAC-002")]
        assert len(rbac002) == 0


# ---------------------------------------------------------------------------
# RBAC-003: Orphaned assignments
# ---------------------------------------------------------------------------


class TestOrphanedAssignments:
    def test_orphaned_principal_detected(self):
        g = _make_graph()
        # Label equals the principal_id → indicates display name was never resolved
        orphan_id = "principal:deleted-user-999"
        g.add_node(
            orphan_id,
            label="deleted-user-999",
            node_type="principal",
            sub_type="User",
            metadata={"principal_id": "deleted-user-999"},
            security_flags=[],
        )
        _add_role(g, "role:reader", "Reader")
        _add_resource(g, "sub:001", "subscription")
        _assign(g, orphan_id, "role:reader", "sub:001")

        findings = SecurityAnalyzer(g).analyze()
        rbac003 = [f for f in findings if f.id.startswith("RBAC-003")]
        assert len(rbac003) >= 1
        assert rbac003[0].severity == Severity.MEDIUM

    def test_known_principal_not_flagged_as_orphan(self):
        g = _make_graph()
        # label differs from principal_id → display name was resolved → not orphaned
        g.add_node(
            "principal:user-123",
            label="Alice Smith",
            node_type="principal",
            sub_type="User",
            metadata={"principal_id": "user-123"},
            security_flags=[],
        )
        _add_role(g, "role:reader", "Reader")
        _add_resource(g, "sub:001", "subscription")
        _assign(g, "principal:user-123", "role:reader", "sub:001")

        findings = SecurityAnalyzer(g).analyze()
        rbac003 = [f for f in findings if f.id.startswith("RBAC-003")]
        assert len(rbac003) == 0


# ---------------------------------------------------------------------------
# RBAC-004: Service principal Owner
# ---------------------------------------------------------------------------


class TestServicePrincipalOwner:
    def test_sp_owner_is_critical(self):
        g = _make_graph()
        _add_principal(g, "principal:my-sp", "ServicePrincipal", "my-app")
        _add_role(g, "role:owner", "Owner")
        _add_resource(g, "sub:001", "subscription")
        _assign(g, "principal:my-sp", "role:owner", "sub:001")

        findings = SecurityAnalyzer(g).analyze()
        rbac004 = [f for f in findings if f.id.startswith("RBAC-004")]
        assert len(rbac004) == 1
        assert rbac004[0].severity == Severity.CRITICAL

    def test_sp_reader_not_flagged(self):
        g = _make_graph()
        _add_principal(g, "principal:my-sp2", "ServicePrincipal", "my-app2")
        _add_role(g, "role:reader", "Reader")
        _add_resource(g, "sub:001", "subscription")
        _assign(g, "principal:my-sp2", "role:reader", "sub:001")

        findings = SecurityAnalyzer(g).analyze()
        rbac004 = [f for f in findings if f.id.startswith("RBAC-004")]
        assert len(rbac004) == 0


# ---------------------------------------------------------------------------
# RBAC-005: Custom role with wildcard
# ---------------------------------------------------------------------------


class TestWildcardCustomRole:
    def test_wildcard_custom_role_detected(self):
        g = _make_graph()
        _add_role(
            g,
            "role:custom-wild",
            "My Custom Role",
            role_type="CustomRole",
            permissions=[{"actions": ["*"], "not_actions": []}],
        )

        findings = SecurityAnalyzer(g).analyze()
        rbac005 = [f for f in findings if f.id.startswith("RBAC-005")]
        assert len(rbac005) == 1
        assert rbac005[0].severity == Severity.HIGH

    def test_custom_role_without_wildcard_not_flagged(self):
        g = _make_graph()
        _add_role(
            g,
            "role:custom-ok",
            "My Safe Role",
            role_type="CustomRole",
            permissions=[{"actions": ["Microsoft.Storage/storageAccounts/read"], "not_actions": []}],
        )

        findings = SecurityAnalyzer(g).analyze()
        rbac005 = [f for f in findings if f.id.startswith("RBAC-005")]
        assert len(rbac005) == 0

    def test_builtin_role_wildcard_not_flagged_by_rbac005(self):
        """Built-in roles with * are not flagged – only custom roles."""
        g = _make_graph()
        _add_role(
            g,
            "role:builtin-wild",
            "Owner",
            role_type="BuiltInRole",
            permissions=[{"actions": ["*"], "not_actions": []}],
        )

        findings = SecurityAnalyzer(g).analyze()
        rbac005 = [f for f in findings if f.id.startswith("RBAC-005")]
        assert len(rbac005) == 0


# ---------------------------------------------------------------------------
# RBAC-006: Low group usage
# ---------------------------------------------------------------------------


class TestGroupAdoption:
    def test_low_group_ratio_flagged(self):
        g = _make_graph()
        # 5 users, 0 groups → ratio 0%
        for i in range(5):
            _add_principal(g, f"principal:u{i}", "User")
            _add_role(g, f"role:r{i}", "Reader")
            _add_resource(g, f"sub:{i}", "subscription")
            _assign(g, f"principal:u{i}", f"role:r{i}", f"sub:{i}")

        findings = SecurityAnalyzer(g).analyze()
        rbac006 = [f for f in findings if f.id == "RBAC-006"]
        assert len(rbac006) == 1
        assert rbac006[0].severity == Severity.LOW

    def test_adequate_group_ratio_not_flagged(self):
        g = _make_graph()
        # 1 user, 4 groups → ratio 80% (above 20% threshold)
        _add_principal(g, "principal:u0", "User")
        for i in range(4):
            _add_principal(g, f"principal:g{i}", "Group")

        findings = SecurityAnalyzer(g).analyze()
        rbac006 = [f for f in findings if f.id == "RBAC-006"]
        assert len(rbac006) == 0

    def test_empty_graph_no_group_finding(self):
        g = _make_graph()
        findings = SecurityAnalyzer(g).analyze()
        rbac006 = [f for f in findings if f.id == "RBAC-006"]
        assert len(rbac006) == 0


# ---------------------------------------------------------------------------
# Security flag propagation
# ---------------------------------------------------------------------------


class TestSecurityFlagPropagation:
    def test_flags_applied_to_affected_nodes(self):
        g = _make_graph()
        _add_principal(g, "principal:sp-evil", "ServicePrincipal", "evil-sp")
        _add_role(g, "role:owner", "Owner")
        _add_resource(g, "sub:001", "subscription")
        _assign(g, "principal:sp-evil", "role:owner", "sub:001")

        SecurityAnalyzer(g).analyze()

        flags = g.nodes["principal:sp-evil"].get("security_flags", [])
        assert any("critical" in f for f in flags)


# ---------------------------------------------------------------------------
# Finding serialisation
# ---------------------------------------------------------------------------


class TestFindingSerialization:
    def test_to_dict_has_required_keys(self):
        finding = Finding(
            id="TEST-001",
            severity=Severity.HIGH,
            title="Test",
            description="Desc",
            affected_nodes=["a", "b"],
            remediation="Fix it",
            references=["https://example.com"],
        )
        d = finding.to_dict()
        assert d["id"] == "TEST-001"
        assert d["severity"] == "high"
        assert d["title"] == "Test"
        assert d["affected_nodes"] == ["a", "b"]
