"""Security analyzer for the Azure RBAC permission graph.

Inspects the graph produced by GraphBuilder and returns structured security
findings with severity ratings, explanations, and remediation suggestions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import networkx as nx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Finding model
# ---------------------------------------------------------------------------


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class Finding:
    """A single security finding on the RBAC graph."""

    id: str
    severity: Severity
    title: str
    description: str
    affected_nodes: list[str] = field(default_factory=list)
    remediation: str = ""
    references: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "affected_nodes": self.affected_nodes,
            "remediation": self.remediation,
            "references": self.references,
        }


# ---------------------------------------------------------------------------
# Rule helpers
# ---------------------------------------------------------------------------

# Well-known privileged built-in role GUIDs
OWNER_ROLE_NAME = "Owner"
CONTRIBUTOR_ROLE_NAME = "Contributor"
USER_ACCESS_ADMIN_ROLE_NAME = "User Access Administrator"

PRIVILEGED_ROLE_NAMES = {OWNER_ROLE_NAME, CONTRIBUTOR_ROLE_NAME, USER_ACCESS_ADMIN_ROLE_NAME}

# Subscription-level scope pattern
_SUBSCRIPTION_SCOPE_PREFIX = "sub:"


def _is_privileged_role(role_label: str) -> bool:
    return any(priv in role_label for priv in PRIVILEGED_ROLE_NAMES)


def _is_subscription_scope(node_id: str) -> bool:
    return node_id.startswith(_SUBSCRIPTION_SCOPE_PREFIX)


# ---------------------------------------------------------------------------
# SecurityAnalyzer
# ---------------------------------------------------------------------------


class SecurityAnalyzer:
    """Runs a suite of security checks against an RBAC graph.

    Usage::

        builder = GraphBuilder.load("graph.json")
        analyzer = SecurityAnalyzer(builder.graph)
        findings = analyzer.analyze()
        for f in findings:
            print(f.severity, f.title)
    """

    def __init__(self, graph: nx.DiGraph) -> None:
        self._graph = graph

    def analyze(self) -> list[Finding]:
        """Run all checks and return the combined list of findings."""
        findings: list[Finding] = []
        findings.extend(self._check_owner_at_subscription())
        findings.extend(self._check_direct_user_assignments())
        findings.extend(self._check_orphaned_assignments())
        findings.extend(self._check_service_principal_owner())
        findings.extend(self._check_broad_wildcard_roles())
        findings.extend(self._check_missing_group_usage())
        findings.extend(self._flag_nodes(findings))
        return findings

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_owner_at_subscription(self) -> list[Finding]:
        """Find principals with Owner role scoped to an entire subscription."""
        results: list[Finding] = []
        for src, role_node, edge_attrs in self._graph.edges(data=True):
            if edge_attrs.get("edge_type") != "assigned":
                continue
            role_data = self._graph.nodes.get(role_node, {})
            role_label = role_data.get("label", "")
            if not _is_privileged_role(role_label):
                continue
            # Check the scoped_to edges from this role node
            for _, scope_node, scope_attrs in self._graph.out_edges(role_node, data=True):
                if scope_attrs.get("edge_type") != "scoped_to":
                    continue
                if not _is_subscription_scope(scope_node):
                    continue
                principal_data = self._graph.nodes.get(src, {})
                results.append(
                    Finding(
                        id=f"RBAC-001-{src}-{scope_node}",
                        severity=Severity.HIGH,
                        title=f"Privileged role '{role_label}' assigned at subscription scope",
                        description=(
                            f"Principal '{principal_data.get('label', src)}' has the "
                            f"'{role_label}' role directly assigned at subscription scope "
                            f"({scope_node}). This violates the principle of least privilege."
                        ),
                        affected_nodes=[src, role_node, scope_node],
                        remediation=(
                            "Reduce scope to the minimum required resource group or resource. "
                            "Consider replacing 'Owner' with a purpose-built custom role. "
                            "Use Azure PIM (Privileged Identity Management) to make the "
                            "assignment eligible rather than active."
                        ),
                        references=[
                            "https://learn.microsoft.com/en-us/azure/role-based-access-control/best-practices",
                            "https://learn.microsoft.com/en-us/azure/active-directory/privileged-identity-management/",
                        ],
                    )
                )
        return results

    def _check_direct_user_assignments(self) -> list[Finding]:
        """Find individual users (not groups) with role assignments."""
        results: list[Finding] = []
        direct_users: dict[str, list[str]] = {}

        for src, _, edge_attrs in self._graph.edges(data=True):
            if edge_attrs.get("edge_type") != "assigned":
                continue
            node_data = self._graph.nodes.get(src, {})
            if node_data.get("sub_type") == "User":
                direct_users.setdefault(src, []).append(
                    edge_attrs.get("metadata", {}).get("assignment_id", "")
                )

        for principal_id, assignment_ids in direct_users.items():
            principal_data = self._graph.nodes.get(principal_id, {})
            results.append(
                Finding(
                    id=f"RBAC-002-{principal_id}",
                    severity=Severity.MEDIUM,
                    title="Direct user role assignment (use groups instead)",
                    description=(
                        f"User '{principal_data.get('label', principal_id)}' has "
                        f"{len(assignment_ids)} direct role assignment(s). "
                        "Direct user assignments make access management harder to audit "
                        "and scale."
                    ),
                    affected_nodes=[principal_id],
                    remediation=(
                        "Assign roles to Azure AD security groups and add the user to the "
                        "appropriate group. This centralises access management and improves "
                        "auditability."
                    ),
                    references=[
                        "https://learn.microsoft.com/en-us/azure/role-based-access-control/best-practices#assign-roles-to-groups-not-users"
                    ],
                )
            )
        return results

    def _check_orphaned_assignments(self) -> list[Finding]:
        """Detect role assignments where the principal node has no display name.

        In practice, this indicates the principal has been deleted from Azure AD
        but the role assignment was not cleaned up.
        """
        results: list[Finding] = []
        for node_id, data in self._graph.nodes(data=True):
            if data.get("node_type") != "principal":
                continue
            # If label == principal_id metadata value, the display name was never resolved –
            # which means the object is likely orphaned.
            meta = data.get("metadata", {})
            if data.get("label") == meta.get("principal_id", "__missing__"):
                out_edges = list(self._graph.out_edges(node_id, data=True))
                if out_edges:
                    results.append(
                        Finding(
                            id=f"RBAC-003-{node_id}",
                            severity=Severity.MEDIUM,
                            title="Possibly orphaned role assignment (unknown principal)",
                            description=(
                                f"Principal ID '{meta.get('principal_id')}' has "
                                f"{len(out_edges)} active role assignment(s) but no matching "
                                "Azure AD object was found. The account may have been deleted."
                            ),
                            affected_nodes=[node_id],
                            remediation=(
                                "Verify whether this Azure AD object still exists. If deleted, "
                                "remove the stale role assignment(s) via the Azure portal or "
                                "`az role assignment delete --assignee <principal-id>`."
                            ),
                            references=[
                                "https://learn.microsoft.com/en-us/azure/role-based-access-control/troubleshooting#role-assignments-with-identity-not-found"
                            ],
                        )
                    )
        return results

    def _check_service_principal_owner(self) -> list[Finding]:
        """Find service principals assigned the Owner role at any scope."""
        results: list[Finding] = []
        for src, role_node, edge_attrs in self._graph.edges(data=True):
            if edge_attrs.get("edge_type") != "assigned":
                continue
            principal_data = self._graph.nodes.get(src, {})
            if principal_data.get("sub_type") != "ServicePrincipal":
                continue
            role_data = self._graph.nodes.get(role_node, {})
            if OWNER_ROLE_NAME in role_data.get("label", ""):
                results.append(
                    Finding(
                        id=f"RBAC-004-{src}",
                        severity=Severity.CRITICAL,
                        title="Service principal assigned Owner role",
                        description=(
                            f"Service principal '{principal_data.get('label', src)}' "
                            "has the Owner role. Compromising this service principal would "
                            "grant an attacker full control."
                        ),
                        affected_nodes=[src, role_node],
                        remediation=(
                            "Replace the Owner assignment with a custom role containing only "
                            "the specific actions the service principal needs. Rotate the "
                            "service principal's credentials immediately and review recent "
                            "audit logs."
                        ),
                        references=[
                            "https://learn.microsoft.com/en-us/azure/active-directory/develop/security-best-practices-for-app-registration"
                        ],
                    )
                )
        return results

    def _check_broad_wildcard_roles(self) -> list[Finding]:
        """Find custom roles that use wildcard (*) actions."""
        results: list[Finding] = []
        for node_id, data in self._graph.nodes(data=True):
            if data.get("node_type") != "role":
                continue
            if data.get("sub_type") != "CustomRole":
                continue
            permissions = data.get("metadata", {}).get("permissions", [])
            for perm in permissions:
                if "*" in perm.get("actions", []):
                    results.append(
                        Finding(
                            id=f"RBAC-005-{node_id}",
                            severity=Severity.HIGH,
                            title="Custom role uses wildcard (*) actions",
                            description=(
                                f"Custom role '{data.get('label', node_id)}' includes a "
                                "wildcard (*) action permission. This effectively grants all "
                                "control-plane operations."
                            ),
                            affected_nodes=[node_id],
                            remediation=(
                                "Replace the wildcard with the minimum set of explicit actions "
                                "the role needs. Use the Azure RBAC documentation to enumerate "
                                "only the required operations."
                            ),
                            references=[
                                "https://learn.microsoft.com/en-us/azure/role-based-access-control/custom-roles"
                            ],
                        )
                    )
                    break  # one finding per role
        return results

    def _check_missing_group_usage(self) -> list[Finding]:
        """High-level check: warn if fewer than 20% of principals are groups."""
        principal_nodes = [
            d for _, d in self._graph.nodes(data=True)
            if d.get("node_type") == "principal"
        ]
        if not principal_nodes:
            return []

        groups = sum(1 for d in principal_nodes if d.get("sub_type") == "Group")
        ratio = groups / len(principal_nodes)
        if ratio < 0.2:
            return [
                Finding(
                    id="RBAC-006",
                    severity=Severity.LOW,
                    title="Low group-based access adoption",
                    description=(
                        f"Only {groups} of {len(principal_nodes)} principals with role "
                        f"assignments are groups ({ratio:.0%}). Best practice recommends "
                        "assigning roles to groups to simplify management."
                    ),
                    affected_nodes=[],
                    remediation=(
                        "Create Azure AD security groups aligned with job functions and "
                        "reassign roles to those groups. Use the persona recommendations "
                        "from this tool's AI advisor to identify groupings."
                    ),
                    references=[
                        "https://learn.microsoft.com/en-us/azure/role-based-access-control/best-practices"
                    ],
                )
            ]
        return []

    # ------------------------------------------------------------------
    # Post-processing
    # ------------------------------------------------------------------

    def _flag_nodes(self, findings: list[Finding]) -> list[Finding]:
        """Annotate graph nodes with security_flags based on findings.

        This method mutates node attributes in-place and returns an empty list
        (it is called last so findings are already complete).
        """
        for finding in findings:
            for node_id in finding.affected_nodes:
                if self._graph.has_node(node_id):
                    flags: list[str] = self._graph.nodes[node_id].get("security_flags", [])
                    flag_str = f"{finding.severity.value}:{finding.id}"
                    if flag_str not in flags:
                        flags.append(flag_str)
                    self._graph.nodes[node_id]["security_flags"] = flags
        return []
