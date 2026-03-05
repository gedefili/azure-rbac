"""Tests for azure_client.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from azure_rbac.azure_client import (
    AzureClient,
    ManagementGroup,
    Principal,
    RoleAssignment,
    RoleDefinition,
    Subscription,
)


# ---------------------------------------------------------------------------
# Credential selection
# ---------------------------------------------------------------------------


class TestCredentialSelection:
    @patch("azure_rbac.azure_client.ManagedIdentityCredential")
    @patch("azure_rbac.azure_client.SubscriptionClient")
    def test_msi_credential_used_when_flag_set(self, mock_sub_client, mock_msi):
        AzureClient(use_msi=True)
        mock_msi.assert_called_once()

    @patch("azure_rbac.azure_client.ClientSecretCredential")
    @patch("azure_rbac.azure_client.SubscriptionClient")
    def test_client_secret_credential_used_when_env_set(
        self, mock_sub_client, mock_csc
    ):
        AzureClient(
            tenant_id="tenant-id",
            client_id="client-id",
            client_secret="secret",
            use_msi=False,
        )
        mock_csc.assert_called_once_with(
            tenant_id="tenant-id",
            client_id="client-id",
            client_secret="secret",
        )

    @patch("azure_rbac.azure_client.DefaultAzureCredential")
    @patch("azure_rbac.azure_client.SubscriptionClient")
    def test_default_credential_used_as_fallback(self, mock_sub_client, mock_dac):
        AzureClient(use_msi=False)
        mock_dac.assert_called_once()


# ---------------------------------------------------------------------------
# list_subscriptions
# ---------------------------------------------------------------------------


class TestListSubscriptions:
    def _mock_sub(self, sub_id: str, display_name: str, state: str) -> MagicMock:
        sub = MagicMock()
        sub.subscription_id = sub_id
        sub.display_name = display_name
        sub.state = state
        return sub

    @patch("azure_rbac.azure_client.DefaultAzureCredential")
    @patch("azure_rbac.azure_client.SubscriptionClient")
    def test_returns_subscriptions(self, mock_sub_client_cls, mock_dac):
        mock_instance = MagicMock()
        mock_instance.subscriptions.list.return_value = [
            self._mock_sub("sub-001", "Dev", "Enabled"),
            self._mock_sub("sub-002", "Prod", "Enabled"),
        ]
        mock_sub_client_cls.return_value = mock_instance

        client = AzureClient(use_msi=False)
        subs = client.list_subscriptions()

        assert len(subs) == 2
        assert subs[0].id == "sub-001"
        assert subs[0].display_name == "Dev"
        assert subs[1].id == "sub-002"

    @patch("azure_rbac.azure_client.DefaultAzureCredential")
    @patch("azure_rbac.azure_client.SubscriptionClient")
    def test_empty_tenant_returns_empty_list(self, mock_sub_client_cls, mock_dac):
        mock_instance = MagicMock()
        mock_instance.subscriptions.list.return_value = []
        mock_sub_client_cls.return_value = mock_instance

        client = AzureClient(use_msi=False)
        assert client.list_subscriptions() == []


# ---------------------------------------------------------------------------
# list_role_assignments
# ---------------------------------------------------------------------------


class TestListRoleAssignments:
    def _mock_ra(
        self,
        ra_id: str,
        principal_id: str,
        principal_type: str,
        role_def_id: str,
        scope: str,
    ) -> MagicMock:
        ra = MagicMock()
        ra.id = ra_id
        ra.principal_id = principal_id
        ra.principal_type = principal_type
        ra.role_definition_id = role_def_id
        ra.scope = scope
        return ra

    @patch("azure_rbac.azure_client.DefaultAzureCredential")
    @patch("azure_rbac.azure_client.SubscriptionClient")
    @patch("azure_rbac.azure_client.AuthorizationManagementClient")
    def test_returns_role_assignments(self, mock_auth_cls, mock_sub_client_cls, mock_dac):
        mock_auth = MagicMock()
        mock_auth.role_assignments.list_for_subscription.return_value = [
            self._mock_ra(
                "ra-001", "user-aaa", "User",
                "/providers/roleDefinitions/owner-id",
                "/subscriptions/sub-001",
            )
        ]
        mock_auth_cls.return_value = mock_auth
        mock_sub_client_cls.return_value = MagicMock()

        client = AzureClient(use_msi=False)
        assignments = client.list_role_assignments("sub-001")

        assert len(assignments) == 1
        assert assignments[0].principal_id == "user-aaa"
        assert assignments[0].principal_type == "User"
        assert assignments[0].scope == "/subscriptions/sub-001"


# ---------------------------------------------------------------------------
# list_role_definitions
# ---------------------------------------------------------------------------


class TestListRoleDefinitions:
    def _mock_rd(self, rd_id: str, name: str, role_type: str) -> MagicMock:
        rd = MagicMock()
        rd.id = rd_id
        rd.role_name = name
        rd.role_type = role_type
        rd.description = "desc"
        perm = MagicMock()
        perm.actions = ["*"]
        perm.not_actions = []
        perm.data_actions = []
        perm.not_data_actions = []
        rd.permissions = [perm]
        return rd

    @patch("azure_rbac.azure_client.DefaultAzureCredential")
    @patch("azure_rbac.azure_client.SubscriptionClient")
    @patch("azure_rbac.azure_client.AuthorizationManagementClient")
    def test_returns_role_definitions(self, mock_auth_cls, mock_sub_client_cls, mock_dac):
        mock_auth = MagicMock()
        mock_auth.role_definitions.list.return_value = [
            self._mock_rd("rd-owner", "Owner", "BuiltInRole"),
            self._mock_rd("rd-custom", "My Custom Role", "CustomRole"),
        ]
        mock_auth_cls.return_value = mock_auth
        mock_sub_client_cls.return_value = MagicMock()

        client = AzureClient(use_msi=False)
        role_defs = client.list_role_definitions("sub-001")

        assert len(role_defs) == 2
        names = {rd.name for rd in role_defs}
        assert "Owner" in names
        assert "My Custom Role" in names


# ---------------------------------------------------------------------------
# Data model defaults
# ---------------------------------------------------------------------------


class TestDataModels:
    def test_subscription_defaults(self):
        sub = Subscription(id="s1", display_name="Sub", state="Enabled")
        assert sub.id == "s1"

    def test_role_definition_defaults(self):
        rd = RoleDefinition(id="r1", name="Reader", role_type="BuiltInRole")
        assert rd.permissions == []
        assert rd.description == ""

    def test_role_assignment_fields(self):
        ra = RoleAssignment(
            id="ra1",
            principal_id="p1",
            principal_type="User",
            role_definition_id="rd1",
            scope="/subscriptions/s1",
        )
        assert ra.scope == "/subscriptions/s1"

    def test_principal_defaults(self):
        p = Principal(id="p1", display_name="Alice", principal_type="User")
        assert p.enabled is True
        assert p.user_principal_name == ""

    def test_management_group_defaults(self):
        mg = ManagementGroup(id="mg1", display_name="Root")
        assert mg.parent_id == ""
