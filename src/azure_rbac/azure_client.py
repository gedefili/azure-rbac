"""Azure API client.

Wraps azure-identity, azure-mgmt-authorization, azure-mgmt-resource, and
msgraph-sdk to expose a single, testable interface used by GraphBuilder.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from azure.identity import (
    ClientSecretCredential,
    DefaultAzureCredential,
    ManagedIdentityCredential,
)
from azure.mgmt.authorization import AuthorizationManagementClient
from azure.mgmt.managementgroups import ManagementGroupsAPI
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.subscription import SubscriptionClient


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class Principal:
    """Represents an Azure AD principal (user, group, or service principal)."""

    id: str
    display_name: str
    principal_type: str  # "User" | "Group" | "ServicePrincipal"
    user_principal_name: str = ""
    enabled: bool = True


@dataclass
class RoleDefinition:
    """Represents an Azure role definition."""

    id: str
    name: str
    role_type: str  # "BuiltInRole" | "CustomRole"
    description: str = ""
    permissions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RoleAssignment:
    """Represents a single Azure role assignment."""

    id: str
    principal_id: str
    principal_type: str
    role_definition_id: str
    scope: str


@dataclass
class Subscription:
    """Represents an Azure subscription."""

    id: str
    display_name: str
    state: str


@dataclass
class ManagementGroup:
    """Represents an Azure management group."""

    id: str
    display_name: str
    parent_id: str = ""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class AzureClient:
    """Thin wrapper around Azure SDK clients.

    Authentication order (checked at construction time):
    1. If AZURE_USE_MSI=true → ManagedIdentityCredential
    2. If AZURE_CLIENT_ID + AZURE_CLIENT_SECRET are set → ClientSecretCredential
    3. Otherwise → DefaultAzureCredential (supports environment, workload identity,
       Azure CLI, etc.)
    """

    def __init__(
        self,
        tenant_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        use_msi: bool | None = None,
    ) -> None:
        self._tenant_id = tenant_id or os.environ.get("AZURE_TENANT_ID", "")
        _client_id = client_id or os.environ.get("AZURE_CLIENT_ID", "")
        _client_secret = client_secret or os.environ.get("AZURE_CLIENT_SECRET", "")
        _use_msi = use_msi if use_msi is not None else (
            os.environ.get("AZURE_USE_MSI", "false").lower() == "true"
        )

        if _use_msi:
            self._credential: Any = ManagedIdentityCredential()
        elif _client_id and _client_secret and self._tenant_id:
            self._credential = ClientSecretCredential(
                tenant_id=self._tenant_id,
                client_id=_client_id,
                client_secret=_client_secret,
            )
        else:
            self._credential = DefaultAzureCredential()

        self._subscription_client = SubscriptionClient(self._credential)

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    def list_subscriptions(self) -> list[Subscription]:
        """Return all subscriptions accessible to the credential."""
        results: list[Subscription] = []
        for sub in self._subscription_client.subscriptions.list():
            results.append(
                Subscription(
                    id=sub.subscription_id or "",
                    display_name=sub.display_name or "",
                    state=str(sub.state) if sub.state else "Unknown",
                )
            )
        return results

    # ------------------------------------------------------------------
    # Management groups
    # ------------------------------------------------------------------

    def list_management_groups(self) -> list[ManagementGroup]:
        """Return all management groups in the tenant."""
        mg_client = ManagementGroupsAPI(self._credential)
        results: list[ManagementGroup] = []
        for group in mg_client.management_groups.list():
            parent_id = ""
            if hasattr(group, "parent") and group.parent:
                parent_id = group.parent.id or ""
            results.append(
                ManagementGroup(
                    id=group.id or "",
                    display_name=group.display_name or "",
                    parent_id=parent_id,
                )
            )
        return results

    # ------------------------------------------------------------------
    # Role assignments & definitions
    # ------------------------------------------------------------------

    def list_role_assignments(self, subscription_id: str) -> list[RoleAssignment]:
        """Return all role assignments for a subscription."""
        auth_client = AuthorizationManagementClient(
            self._credential, subscription_id
        )
        results: list[RoleAssignment] = []
        for ra in auth_client.role_assignments.list_for_subscription():
            results.append(
                RoleAssignment(
                    id=ra.id or "",
                    principal_id=ra.principal_id or "",
                    principal_type=ra.principal_type or "Unknown",
                    role_definition_id=ra.role_definition_id or "",
                    scope=ra.scope or "",
                )
            )
        return results

    def list_role_definitions(self, subscription_id: str) -> list[RoleDefinition]:
        """Return all role definitions visible from a subscription."""
        auth_client = AuthorizationManagementClient(
            self._credential, subscription_id
        )
        scope = f"/subscriptions/{subscription_id}"
        results: list[RoleDefinition] = []
        for rd in auth_client.role_definitions.list(scope):
            permissions = []
            if rd.permissions:
                for perm in rd.permissions:
                    permissions.append(
                        {
                            "actions": list(perm.actions or []),
                            "not_actions": list(perm.not_actions or []),
                            "data_actions": list(perm.data_actions or []),
                            "not_data_actions": list(perm.not_data_actions or []),
                        }
                    )
            results.append(
                RoleDefinition(
                    id=rd.id or "",
                    name=rd.role_name or "",
                    role_type=rd.role_type or "BuiltInRole",
                    description=rd.description or "",
                    permissions=permissions,
                )
            )
        return results

    # ------------------------------------------------------------------
    # Resource groups
    # ------------------------------------------------------------------

    def list_resource_groups(self, subscription_id: str) -> list[dict[str, str]]:
        """Return resource group names and locations for a subscription."""
        rmc = ResourceManagementClient(self._credential, subscription_id)
        return [
            {"name": rg.name or "", "location": rg.location or ""}
            for rg in rmc.resource_groups.list()
        ]
