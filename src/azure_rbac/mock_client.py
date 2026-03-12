"""Mock Azure client that serves data from a Fauxterprise fixture file.

This is a drop-in replacement for :class:`azure_rbac.azure_client.AzureClient`
that reads pre-generated JSON fixture data instead of calling Azure APIs.
It allows the full azure-rbac pipeline (build → analyze → advise → dashboard)
to run locally without an Azure subscription.

Usage::

    from azure_rbac.mock_client import MockAzureClient

    client = MockAzureClient("fauxterprise/fixture.json")
    subs = client.list_subscriptions()           # works identically
    assignments = client.list_role_assignments("sub-id")
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from azure_rbac.azure_client import (
    ManagementGroup,
    Principal,
    RoleAssignment,
    RoleDefinition,
    Subscription,
)

logger = logging.getLogger(__name__)


class MockAzureClient:
    """AzureClient-compatible mock backed by a JSON fixture file.

    Implements the same public API as
    :class:`~azure_rbac.azure_client.AzureClient` so it can be used
    anywhere ``AzureClient`` is expected.
    """

    def __init__(self, fixture_path: str | Path) -> None:
        path = Path(fixture_path)
        if not path.exists():
            msg = f"Fixture file not found: {path}"
            raise FileNotFoundError(msg)

        self._data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        self._tenant_id = self._data.get("tenant_id", "")
        logger.info(
            "MockAzureClient loaded fixture: %d subs, %d role assignments",
            len(self._data.get("subscriptions", [])),
            len(self._data.get("role_assignments", [])),
        )

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    def list_subscriptions(self) -> list[Subscription]:
        return [
            Subscription(
                id=s["subscription_id"],
                display_name=s["display_name"],
                state=s.get("state", "Enabled"),
            )
            for s in self._data.get("subscriptions", [])
        ]

    # ------------------------------------------------------------------
    # Management groups
    # ------------------------------------------------------------------

    def list_management_groups(self) -> list[ManagementGroup]:
        return [
            ManagementGroup(
                id=mg["id"],
                display_name=mg["display_name"],
                parent_id=mg.get("parent_id", ""),
            )
            for mg in self._data.get("management_groups", [])
        ]

    # ------------------------------------------------------------------
    # Role assignments & definitions
    # ------------------------------------------------------------------

    def list_role_assignments(self, subscription_id: str) -> list[RoleAssignment]:
        by_sub = self._data.get("role_assignments_by_subscription", {})
        raw = by_sub.get(subscription_id, [])
        return [
            RoleAssignment(
                id=ra["id"],
                principal_id=ra["principal_id"],
                principal_type=ra["principal_type"],
                role_definition_id=ra["role_definition_id"],
                scope=ra["scope"],
            )
            for ra in raw
        ]

    def list_role_definitions(self, subscription_id: str) -> list[RoleDefinition]:
        return [
            RoleDefinition(
                id=rd["id"],
                name=rd["name"],
                role_type=rd.get("role_type", "BuiltInRole"),
                description=rd.get("description", ""),
                permissions=rd.get("permissions", []),
            )
            for rd in self._data.get("role_definitions", [])
        ]

    # ------------------------------------------------------------------
    # Resource groups
    # ------------------------------------------------------------------

    def list_resource_groups(self, subscription_id: str) -> list[dict[str, str]]:
        by_sub = self._data.get("resource_groups_by_subscription", {})
        return by_sub.get(subscription_id, [])

    # ------------------------------------------------------------------
    # Additional helpers for tests/introspection
    # ------------------------------------------------------------------

    def list_users(self) -> list[Principal]:
        """Return all AD users from the fixture (not part of AzureClient API)."""
        return [
            Principal(
                id=u["object_id"],
                display_name=u["display_name"],
                principal_type="User",
                user_principal_name=u.get("user_principal_name", ""),
                enabled=u.get("enabled", True),
            )
            for u in self._data.get("users", [])
        ]

    def list_groups(self) -> list[Principal]:
        """Return all AD groups from the fixture (not part of AzureClient API)."""
        return [
            Principal(
                id=g["object_id"],
                display_name=g["display_name"],
                principal_type="Group",
            )
            for g in self._data.get("groups", {}).values()
        ]

    @property
    def fixture_data(self) -> dict[str, Any]:
        """Raw fixture data for advanced introspection."""
        return self._data
