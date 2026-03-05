"""Permission graph builder.

Constructs a NetworkX directed graph where:
- Nodes represent principals (users, groups, service principals), resources
  (subscriptions, management groups, resource groups), and roles.
- Edges represent role assignments linking a principal to a resource via a role.

The resulting graph can be serialised to JSON for the D3.js dashboard or
stored as a snapshot in Azure Blob Storage.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import networkx as nx

from azure_rbac.azure_client import AzureClient, RoleAssignment, RoleDefinition, Subscription

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node / Edge type constants
# ---------------------------------------------------------------------------

NODE_PRINCIPAL = "principal"
NODE_RESOURCE = "resource"
NODE_ROLE = "role"

EDGE_ASSIGNED = "assigned"       # principal -> role
EDGE_SCOPED_TO = "scoped_to"     # role assignment -> resource


# ---------------------------------------------------------------------------
# Graph serialisation helpers
# ---------------------------------------------------------------------------


@dataclass
class GraphNode:
    """Serialisable graph node."""

    id: str
    label: str
    node_type: str                     # principal | resource | role
    sub_type: str = ""                 # User | Group | ServicePrincipal | subscription | …
    metadata: dict[str, Any] = field(default_factory=dict)
    security_flags: list[str] = field(default_factory=list)


@dataclass
class GraphEdge:
    """Serialisable graph edge."""

    source: str
    target: str
    edge_type: str
    label: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# GraphBuilder
# ---------------------------------------------------------------------------


class GraphBuilder:
    """Builds and manages the Azure RBAC permission graph.

    Usage::

        client = AzureClient()
        builder = GraphBuilder(client)
        builder.build()
        builder.save("graph.json")
    """

    def __init__(self, client: AzureClient | None = None) -> None:
        self._client = client or AzureClient()
        self._graph: nx.DiGraph = nx.DiGraph()
        # Internal caches
        self._role_defs: dict[str, RoleDefinition] = {}
        self._subscriptions: list[Subscription] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self) -> nx.DiGraph:
        """Discover the full tenant RBAC structure and build the graph.

        Returns the populated NetworkX DiGraph.
        """
        logger.info("Starting tenant-level RBAC graph build…")
        self._subscriptions = self._client.list_subscriptions()
        logger.info("Found %d subscription(s)", len(self._subscriptions))

        # Add subscription nodes
        for sub in self._subscriptions:
            self._add_resource_node(
                node_id=f"sub:{sub.id}",
                label=sub.display_name,
                sub_type="subscription",
                metadata={"subscription_id": sub.id, "state": sub.state},
            )

        # Collect management groups
        try:
            for mg in self._client.list_management_groups():
                self._add_resource_node(
                    node_id=f"mg:{mg.id}",
                    label=mg.display_name,
                    sub_type="management_group",
                    metadata={"parent_id": mg.parent_id},
                )
        except Exception:  # noqa: BLE001
            logger.warning("Could not enumerate management groups – continuing.")

        # Per-subscription: role definitions, assignments, resource groups
        for sub in self._subscriptions:
            self._process_subscription(sub)

        logger.info(
            "Graph built: %d nodes, %d edges",
            self._graph.number_of_nodes(),
            self._graph.number_of_edges(),
        )
        return self._graph

    def to_dict(self) -> dict[str, Any]:
        """Serialise the graph to a JSON-compatible dictionary.

        The format is understood by the D3.js dashboard (nodes + links arrays).
        """
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []

        for node_id, attrs in self._graph.nodes(data=True):
            nodes.append(
                {
                    "id": node_id,
                    "label": attrs.get("label", node_id),
                    "node_type": attrs.get("node_type", "unknown"),
                    "sub_type": attrs.get("sub_type", ""),
                    "metadata": attrs.get("metadata", {}),
                    "security_flags": attrs.get("security_flags", []),
                }
            )

        for src, dst, attrs in self._graph.edges(data=True):
            edges.append(
                {
                    "source": src,
                    "target": dst,
                    "edge_type": attrs.get("edge_type", ""),
                    "label": attrs.get("label", ""),
                    "metadata": attrs.get("metadata", {}),
                }
            )

        return {"nodes": nodes, "links": edges}

    def save(self, path: str | Path) -> None:
        """Write the graph JSON to *path*."""
        data = self.to_dict()
        Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Graph saved to %s", path)

    @classmethod
    def load(cls, path: str | Path) -> "GraphBuilder":
        """Load a previously saved graph from *path* (no API calls made)."""
        builder = cls.__new__(cls)
        builder._graph = nx.DiGraph()
        builder._role_defs = {}
        builder._subscriptions = []
        builder._client = None  # type: ignore[assignment]

        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for node in data.get("nodes", []):
            builder._graph.add_node(
                node["id"],
                label=node["label"],
                node_type=node["node_type"],
                sub_type=node["sub_type"],
                metadata=node["metadata"],
                security_flags=node["security_flags"],
            )
        for link in data.get("links", []):
            builder._graph.add_edge(
                link["source"],
                link["target"],
                edge_type=link["edge_type"],
                label=link["label"],
                metadata=link["metadata"],
            )
        return builder

    # ------------------------------------------------------------------
    # Graph accessors
    # ------------------------------------------------------------------

    @property
    def graph(self) -> nx.DiGraph:
        """The underlying NetworkX DiGraph."""
        return self._graph

    def get_principals(self) -> list[dict[str, Any]]:
        """Return all principal nodes."""
        return [
            {"id": n, **d}
            for n, d in self._graph.nodes(data=True)
            if d.get("node_type") == NODE_PRINCIPAL
        ]

    def get_resources(self) -> list[dict[str, Any]]:
        """Return all resource nodes."""
        return [
            {"id": n, **d}
            for n, d in self._graph.nodes(data=True)
            if d.get("node_type") == NODE_RESOURCE
        ]

    def get_role_assignments_for_principal(
        self, principal_id: str
    ) -> list[dict[str, Any]]:
        """Return all role assignment edges originating from *principal_id*."""
        return [
            {"source": src, "target": dst, **attrs}
            for src, dst, attrs in self._graph.out_edges(principal_id, data=True)
        ]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _process_subscription(self, sub: Subscription) -> None:
        logger.debug("Processing subscription: %s", sub.display_name)

        # Cache role definitions
        try:
            for rd in self._client.list_role_definitions(sub.id):
                self._role_defs[rd.id] = rd
                self._add_role_node(rd)
        except Exception:  # noqa: BLE001
            logger.warning("Could not list role definitions for %s", sub.id)

        # Resource groups
        try:
            for rg in self._client.list_resource_groups(sub.id):
                rg_id = f"rg:{sub.id}:{rg['name']}"
                self._add_resource_node(
                    node_id=rg_id,
                    label=rg["name"],
                    sub_type="resource_group",
                    metadata={"subscription_id": sub.id, "location": rg["location"]},
                )
                # Resource group is contained in subscription
                self._graph.add_edge(
                    f"sub:{sub.id}",
                    rg_id,
                    edge_type="contains",
                    label="contains",
                    metadata={},
                )
        except Exception:  # noqa: BLE001
            logger.warning("Could not list resource groups for %s", sub.id)

        # Role assignments
        try:
            assignments = self._client.list_role_assignments(sub.id)
        except Exception:  # noqa: BLE001
            logger.warning("Could not list role assignments for %s", sub.id)
            return

        for ra in assignments:
            self._add_assignment(ra, sub)

    def _add_assignment(
        self, ra: RoleAssignment, sub: Subscription
    ) -> None:
        """Add principal + assignment edges for a single role assignment."""
        principal_node_id = f"principal:{ra.principal_id}"

        # Ensure principal node exists
        if not self._graph.has_node(principal_node_id):
            self._graph.add_node(
                principal_node_id,
                label=ra.principal_id,  # display_name resolved via Graph API in future
                node_type=NODE_PRINCIPAL,
                sub_type=ra.principal_type,
                metadata={"principal_id": ra.principal_id},
                security_flags=[],
            )

        # Resolve role node
        role_node_id = f"role:{ra.role_definition_id}"
        if not self._graph.has_node(role_node_id):
            # Role definition not yet cached – create placeholder
            self._graph.add_node(
                role_node_id,
                label=ra.role_definition_id,
                node_type=NODE_ROLE,
                sub_type="unknown",
                metadata={},
                security_flags=[],
            )

        # Resolve scope node
        scope_node_id = self._scope_to_node_id(ra.scope, sub)

        # principal --[assigned]--> role
        self._graph.add_edge(
            principal_node_id,
            role_node_id,
            edge_type=EDGE_ASSIGNED,
            label="assigned",
            metadata={"assignment_id": ra.id, "scope": ra.scope},
        )

        # role --[scoped_to]--> resource
        self._graph.add_edge(
            role_node_id,
            scope_node_id,
            edge_type=EDGE_SCOPED_TO,
            label="scoped to",
            metadata={"assignment_id": ra.id},
        )

    def _scope_to_node_id(self, scope: str, sub: Subscription) -> str:
        """Convert an assignment scope string to a graph node id, creating the node if needed."""
        parts = scope.strip("/").split("/")

        if len(parts) == 2 and parts[0].lower() == "subscriptions":
            node_id = f"sub:{parts[1]}"
        elif (
            len(parts) >= 4
            and parts[0].lower() == "subscriptions"
            and parts[2].lower() == "resourcegroups"
        ):
            node_id = f"rg:{parts[1]}:{parts[3]}"
        elif scope.startswith("/providers/Microsoft.Management/managementGroups/"):
            node_id = f"mg:{scope}"
        else:
            # Generic resource scope
            node_id = f"resource:{scope}"

        if not self._graph.has_node(node_id):
            self._add_resource_node(
                node_id=node_id,
                label=parts[-1] if parts else scope,
                sub_type="resource",
                metadata={"scope": scope, "subscription_id": sub.id},
            )

        return node_id

    def _add_resource_node(
        self,
        node_id: str,
        label: str,
        sub_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self._graph.has_node(node_id):
            self._graph.add_node(
                node_id,
                label=label,
                node_type=NODE_RESOURCE,
                sub_type=sub_type,
                metadata=metadata or {},
                security_flags=[],
            )

    def _add_role_node(self, rd: RoleDefinition) -> None:
        node_id = f"role:{rd.id}"
        if not self._graph.has_node(node_id):
            self._graph.add_node(
                node_id,
                label=rd.name,
                node_type=NODE_ROLE,
                sub_type=rd.role_type,
                metadata={
                    "description": rd.description,
                    "permissions": rd.permissions,
                },
                security_flags=[],
            )
