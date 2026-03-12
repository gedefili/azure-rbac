"""Integration tests using the Fauxterprise fixture.

These tests verify the full pipeline (build → analyze) works end-to-end
against the simulated enterprise environment without any Azure credentials.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Generate fixture once per test session
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def fixture_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate the Fauxterprise fixture and return the path."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fauxterprise"))
    from generate_fixture import generate_fixture

    data = generate_fixture()
    path = tmp_path_factory.mktemp("fauxterprise") / "fixture.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


@pytest.fixture(scope="session")
def fixture_data(fixture_path: Path) -> dict:
    return json.loads(fixture_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Fixture data integrity
# ---------------------------------------------------------------------------


class TestFixtureIntegrity:
    """Verify the generated fixture matches the Terraform specification."""

    def test_has_100_users(self, fixture_data: dict) -> None:
        assert len(fixture_data["users"]) == 100

    def test_has_15_groups(self, fixture_data: dict) -> None:
        assert len(fixture_data["groups"]) == 15

    def test_has_5_service_principals(self, fixture_data: dict) -> None:
        assert len(fixture_data["service_principals"]) == 5

    def test_has_11_management_groups(self, fixture_data: dict) -> None:
        assert len(fixture_data["management_groups"]) == 11

    def test_has_10_subscriptions(self, fixture_data: dict) -> None:
        assert len(fixture_data["subscriptions"]) == 10

    def test_has_role_definitions(self, fixture_data: dict) -> None:
        # At least the 18 core built-in roles, plus any extras discovered
        assert len(fixture_data["role_definitions"]) >= 18

    def test_role_assignments_non_empty(self, fixture_data: dict) -> None:
        assert len(fixture_data["role_assignments"]) > 100

    def test_management_group_hierarchy(self, fixture_data: dict) -> None:
        """Root should have no parent; others should."""
        mgs = {mg["key"]: mg for mg in fixture_data["management_groups"]}
        assert mgs["root"]["parent_id"] == ""
        assert "enterprise" in mgs["platform"]["parent_id"]

    def test_subscription_resource_groups(self, fixture_data: dict) -> None:
        """Each subscription should have resource groups."""
        for sub in fixture_data["subscriptions"]:
            sub_id = sub["subscription_id"]
            rgs = fixture_data["resource_groups_by_subscription"].get(sub_id, [])
            assert len(rgs) >= 2, f"Sub {sub['display_name']} has too few RGs"

    def test_group_memberships(self, fixture_data: dict) -> None:
        """Every group should have at least one member."""
        for name, group in fixture_data["groups"].items():
            assert len(group["members"]) > 0, f"Group {name} has no members"

    def test_user_upn_format(self, fixture_data: dict) -> None:
        for user in fixture_data["users"]:
            assert "@fauxterprise.onmicrosoft.com" in user["user_principal_name"]

    def test_fixture_is_deterministic(self, fixture_path: Path) -> None:
        """Running the generator twice should produce identical output."""
        from generate_fixture import generate_fixture
        data1 = generate_fixture()
        data2 = generate_fixture()
        assert json.dumps(data1, sort_keys=True) == json.dumps(data2, sort_keys=True)


# ---------------------------------------------------------------------------
# MockAzureClient
# ---------------------------------------------------------------------------


class TestMockAzureClient:
    """Verify MockAzureClient returns correctly typed objects."""

    def test_list_subscriptions(self, fixture_path: Path) -> None:
        from azure_rbac.mock_client import MockAzureClient
        client = MockAzureClient(fixture_path)
        subs = client.list_subscriptions()
        assert len(subs) == 10
        assert all(s.state == "Enabled" for s in subs)

    def test_list_management_groups(self, fixture_path: Path) -> None:
        from azure_rbac.mock_client import MockAzureClient
        client = MockAzureClient(fixture_path)
        mgs = client.list_management_groups()
        assert len(mgs) == 11
        names = {mg.display_name for mg in mgs}
        assert "faux-enterprise" in names

    def test_list_role_assignments_per_sub(self, fixture_path: Path, fixture_data: dict) -> None:
        from azure_rbac.mock_client import MockAzureClient
        client = MockAzureClient(fixture_path)
        total = 0
        for sub in client.list_subscriptions():
            ras = client.list_role_assignments(sub.id)
            total += len(ras)
            for ra in ras:
                assert ra.scope.startswith(f"/subscriptions/{sub.id}")
        assert total > 100

    def test_list_role_definitions(self, fixture_path: Path) -> None:
        from azure_rbac.mock_client import MockAzureClient
        client = MockAzureClient(fixture_path)
        subs = client.list_subscriptions()
        defs = client.list_role_definitions(subs[0].id)
        assert len(defs) >= 18
        names = {rd.name for rd in defs}
        assert "Owner" in names
        assert "Reader" in names
        assert "Contributor" in names

    def test_list_resource_groups(self, fixture_path: Path) -> None:
        from azure_rbac.mock_client import MockAzureClient
        client = MockAzureClient(fixture_path)
        subs = client.list_subscriptions()
        rgs = client.list_resource_groups(subs[0].id)
        assert len(rgs) >= 2

    def test_missing_fixture_raises(self) -> None:
        from azure_rbac.mock_client import MockAzureClient
        with pytest.raises(FileNotFoundError):
            MockAzureClient("/nonexistent/fixture.json")


# ---------------------------------------------------------------------------
# Full pipeline: build → analyze
# ---------------------------------------------------------------------------


class TestFullPipeline:
    """End-to-end test using the fixture through the real GraphBuilder + SecurityAnalyzer."""

    def test_build_and_analyze(self, fixture_path: Path, tmp_path: Path) -> None:
        from azure_rbac.graph_builder import GraphBuilder
        from azure_rbac.mock_client import MockAzureClient
        from azure_rbac.security_analyzer import SecurityAnalyzer

        # Build
        client = MockAzureClient(fixture_path)
        builder = GraphBuilder(client)
        graph = builder.build()

        assert graph.number_of_nodes() > 0
        assert graph.number_of_edges() > 0

        # Save and reload
        graph_path = tmp_path / "graph.json"
        builder.save(graph_path)
        assert graph_path.exists()

        reloaded = GraphBuilder.load(graph_path)
        assert reloaded.graph.number_of_nodes() == graph.number_of_nodes()

        # Analyze
        analyzer = SecurityAnalyzer(graph)
        findings = analyzer.analyze()
        assert len(findings) > 0, "Analyzer should find issues in the messy fauxterprise env"

    def test_build_produces_principals(self, fixture_path: Path) -> None:
        from azure_rbac.graph_builder import GraphBuilder
        from azure_rbac.mock_client import MockAzureClient

        client = MockAzureClient(fixture_path)
        builder = GraphBuilder(client)
        builder.build()

        principals = builder.get_principals()
        assert len(principals) > 0

    def test_build_produces_resources(self, fixture_path: Path) -> None:
        from azure_rbac.graph_builder import GraphBuilder
        from azure_rbac.mock_client import MockAzureClient

        client = MockAzureClient(fixture_path)
        builder = GraphBuilder(client)
        builder.build()

        resources = builder.get_resources()
        assert len(resources) > 0


# ---------------------------------------------------------------------------
# Terraform → Fixture linkage tests
# ---------------------------------------------------------------------------


class TestTerraformLinkage:
    """Verify the fixture is derived from Terraform and tracks changes."""

    @staticmethod
    def _tf_root() -> Path:
        return Path(__file__).resolve().parent.parent / "fauxterprise"

    def test_parser_reads_identity_data(self) -> None:
        """Parser should extract first_names, groups, etc. from .tf files."""
        import sys
        sys.path.insert(0, str(self._tf_root()))
        from terraform_parser import parse_fauxterprise

        tf = parse_fauxterprise(self._tf_root())
        assert len(tf.first_names) == 20
        assert len(tf.last_names) == 20
        assert "platform-admins" in tf.groups
        assert "security-team" in tf.groups

    def test_parser_reads_subscriptions(self) -> None:
        import sys
        sys.path.insert(0, str(self._tf_root()))
        from terraform_parser import parse_fauxterprise

        tf = parse_fauxterprise(self._tf_root())
        assert "connectivity" in tf.subscriptions
        assert "prod_app1" in tf.subscriptions
        assert len(tf.subscriptions) == 10

    def test_parser_reads_management_groups(self) -> None:
        import sys
        sys.path.insert(0, str(self._tf_root()))
        from terraform_parser import parse_fauxterprise

        tf = parse_fauxterprise(self._tf_root())
        mg_keys = {mg.key for mg in tf.management_group_defs}
        assert "root" in mg_keys
        assert "platform" in mg_keys
        assert len(tf.management_group_defs) == 11

    def test_parser_reads_role_assignments(self) -> None:
        import sys
        sys.path.insert(0, str(self._tf_root()))
        from terraform_parser import parse_fauxterprise

        tf = parse_fauxterprise(self._tf_root())
        ra_names = {ra.resource_name for ra in tf.role_assignment_defs}
        assert "break_glass_prod1" in ra_names
        assert "shadow_admin_prod2" in ra_names
        assert len(tf.role_assignment_defs) > 20

    def test_fixture_user_count_tracks_name_lists(self) -> None:
        """If first_names has 20 entries, we get 100 users (20×5 from cycling)."""
        import sys
        sys.path.insert(0, str(self._tf_root()))
        from terraform_parser import parse_fauxterprise

        tf = parse_fauxterprise(self._tf_root())
        n_first = len(tf.first_names)
        expected_users = n_first * (100 // n_first)
        from generate_fixture import generate_fixture
        fixture = generate_fixture(self._tf_root())
        assert len(fixture["users"]) == expected_users

    def test_fixture_group_count_tracks_terraform(self) -> None:
        """Number of groups in fixture equals the groups map in identity locals."""
        import sys
        sys.path.insert(0, str(self._tf_root()))
        from terraform_parser import parse_fauxterprise

        tf = parse_fauxterprise(self._tf_root())
        from generate_fixture import generate_fixture
        fixture = generate_fixture(self._tf_root())
        assert len(fixture["groups"]) == len(tf.groups)

    def test_fixture_subscription_count_tracks_terraform(self) -> None:
        """Subscriptions in fixture equals subscriptions in Terraform locals."""
        import sys
        sys.path.insert(0, str(self._tf_root()))
        from terraform_parser import parse_fauxterprise

        tf = parse_fauxterprise(self._tf_root())
        from generate_fixture import generate_fixture
        fixture = generate_fixture(self._tf_root())
        assert len(fixture["subscriptions"]) == len(tf.subscriptions)

    def test_scenarios_json_matches_terraform(self) -> None:
        """Every scenario in scenarios.json references an existing TF source."""
        scenarios_path = self._tf_root() / "scenarios.json"
        assert scenarios_path.exists(), "scenarios.json must exist"
        import json
        scenarios = json.loads(scenarios_path.read_text(encoding="utf-8"))
        assert len(scenarios["scenarios"]) >= 15
        for s in scenarios["scenarios"]:
            assert "id" in s
            assert "terraform_source" in s
