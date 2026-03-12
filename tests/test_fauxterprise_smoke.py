"""Smoke tests for the Fauxterprise fixture pipeline.

Validates the full chain: Terraform parsing → fixture generation → scenario
documentation.  These tests ensure the pipeline is self-consistent and that
every artefact produced from the Terraform source is valid.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAUX_ROOT = Path(__file__).resolve().parent.parent / "fauxterprise"


@pytest.fixture(scope="module", autouse=True)
def _ensure_faux_on_path() -> None:
    if str(FAUX_ROOT) not in sys.path:
        sys.path.insert(0, str(FAUX_ROOT))


@pytest.fixture(scope="module")
def tf_data():
    from terraform_parser import parse_fauxterprise
    return parse_fauxterprise(FAUX_ROOT)


@pytest.fixture(scope="module")
def fixture_data():
    from generate_fixture import generate_fixture
    return generate_fixture(FAUX_ROOT)


@pytest.fixture(scope="module")
def scenarios():
    path = FAUX_ROOT / "scenarios.json"
    return json.loads(path.read_text(encoding="utf-8"))


# ═══════════════════════════════════════════════════════════════════════════
# 1. Terraform parser smoke
# ═══════════════════════════════════════════════════════════════════════════


class TestParserSmoke:
    """Parser must extract structured data from every .tf module."""

    def test_identity_first_names(self, tf_data) -> None:
        assert len(tf_data.first_names) == 20

    def test_identity_last_names(self, tf_data) -> None:
        assert len(tf_data.last_names) == 20

    def test_identity_departments(self, tf_data) -> None:
        assert len(tf_data.departments) == 10

    def test_identity_job_titles(self, tf_data) -> None:
        assert len(tf_data.job_titles) == 20

    def test_groups_parsed(self, tf_data) -> None:
        assert len(tf_data.groups) == 15
        assert "platform-admins" in tf_data.groups
        assert "security-team" in tf_data.groups
        assert "keyvault-admins" in tf_data.groups

    def test_dept_to_group_mapping(self, tf_data) -> None:
        assert len(tf_data.dept_to_group) == 10
        assert tf_data.dept_to_group["Platform Engineering"] == "platform-admins"

    def test_service_principals(self, tf_data) -> None:
        assert len(tf_data.service_principal_names) == 5
        assert "deploy-pipeline" in tf_data.service_principal_names

    def test_membership_rules(self, tf_data) -> None:
        dept_rules = [r for r in tf_data.membership_rules if r.rule_type == "dept"]
        modulo_rules = [r for r in tf_data.membership_rules if r.rule_type == "modulo"]
        assert len(dept_rules) == 1
        assert len(modulo_rules) >= 5

    def test_management_groups(self, tf_data) -> None:
        assert len(tf_data.management_group_defs) == 11
        keys = {mg.key for mg in tf_data.management_group_defs}
        assert "root" in keys
        assert "platform" in keys
        assert "decommissioned" in keys

    def test_subscriptions(self, tf_data) -> None:
        assert len(tf_data.subscriptions) == 10
        assert "connectivity" in tf_data.subscriptions
        assert "prod_app1" in tf_data.subscriptions
        assert "decommissioned" in tf_data.subscriptions

    def test_role_definitions(self, tf_data) -> None:
        assert len(tf_data.role_definitions) == 18
        assert "owner" in tf_data.role_definitions
        assert "contributor" in tf_data.role_definitions

    def test_role_assignment_defs(self, tf_data) -> None:
        assert len(tf_data.role_assignment_defs) > 20
        names = {ra.resource_name for ra in tf_data.role_assignment_defs}
        assert "break_glass_prod1" in names
        assert "shadow_admin_prod2" in names
        assert "stale_decomm" in names

    def test_prefix_and_domain(self, tf_data) -> None:
        assert tf_data.prefix == "faux"
        assert "fauxterprise" in tf_data.domain


# ═══════════════════════════════════════════════════════════════════════════
# 2. Fixture generation smoke
# ═══════════════════════════════════════════════════════════════════════════


class TestFixtureSmoke:
    """Generated fixture must be complete, self-consistent, and deterministic."""

    def test_meta_section(self, fixture_data) -> None:
        meta = fixture_data["_meta"]
        assert "terraform" in meta["source"].lower() or "hcl" in meta["source"].lower()
        assert meta["prefix"] == "faux"

    def test_user_count(self, fixture_data) -> None:
        assert len(fixture_data["users"]) == 100

    def test_user_structure(self, fixture_data) -> None:
        u = fixture_data["users"][0]
        assert "object_id" in u
        assert "display_name" in u
        assert "user_principal_name" in u
        assert "department" in u
        assert u["principal_type"] == "User"
        assert u["user_principal_name"].endswith("@fauxterprise.onmicrosoft.com")

    def test_group_count(self, fixture_data) -> None:
        assert len(fixture_data["groups"]) == 15

    def test_every_group_has_members(self, fixture_data) -> None:
        for name, group in fixture_data["groups"].items():
            assert len(group["members"]) > 0, f"Group {name} has no members"

    def test_service_principal_count(self, fixture_data) -> None:
        assert len(fixture_data["service_principals"]) == 5

    def test_management_group_count(self, fixture_data) -> None:
        assert len(fixture_data["management_groups"]) == 11

    def test_management_group_hierarchy_root(self, fixture_data) -> None:
        mgs = {mg["key"]: mg for mg in fixture_data["management_groups"]}
        assert mgs["root"]["parent_id"] == ""

    def test_management_group_hierarchy_children(self, fixture_data) -> None:
        mgs = {mg["key"]: mg for mg in fixture_data["management_groups"]}
        for key in ("platform", "landing_zones", "sandbox", "decommissioned"):
            assert mgs[key]["parent_id"] != "", f"{key} should have a parent"
            assert "enterprise" in mgs[key]["parent_id"]

    def test_subscription_count(self, fixture_data) -> None:
        assert len(fixture_data["subscriptions"]) == 10

    def test_subscription_resource_groups(self, fixture_data) -> None:
        for sub in fixture_data["subscriptions"]:
            sub_id = sub["subscription_id"]
            rgs = fixture_data["resource_groups_by_subscription"].get(sub_id, [])
            assert len(rgs) >= 2, f"Sub {sub['display_name']} has too few RGs"

    def test_role_definitions_minimum(self, fixture_data) -> None:
        defs = fixture_data["role_definitions"]
        assert len(defs) >= 18
        names = {rd["name"] for rd in defs}
        for required in ("Owner", "Contributor", "Reader", "User Access Administrator"):
            assert required in names, f"Missing built-in role: {required}"

    def test_role_assignments_count(self, fixture_data) -> None:
        assert len(fixture_data["role_assignments"]) > 100

    def test_role_assignments_have_required_fields(self, fixture_data) -> None:
        for ra in fixture_data["role_assignments"][:20]:
            assert "principal_id" in ra
            assert "principal_type" in ra
            assert "role_definition_id" in ra
            assert "scope" in ra
            assert ra["scope"].startswith("/subscriptions/")

    def test_role_assignments_by_subscription_populated(self, fixture_data) -> None:
        by_sub = fixture_data["role_assignments_by_subscription"]
        total = sum(len(v) for v in by_sub.values())
        assert total == len(fixture_data["role_assignments"])

    def test_deterministic(self, fixture_data) -> None:
        from generate_fixture import generate_fixture
        second = generate_fixture(FAUX_ROOT)
        assert json.dumps(fixture_data, sort_keys=True) == json.dumps(second, sort_keys=True)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Scenarios documentation smoke
# ═══════════════════════════════════════════════════════════════════════════


class TestScenariosSmoke:
    """scenarios.json and SCENARIOS.md must be present and consistent."""

    def test_scenarios_json_exists(self) -> None:
        assert (FAUX_ROOT / "scenarios.json").exists()

    def test_scenarios_md_exists(self) -> None:
        assert (FAUX_ROOT / "SCENARIOS.md").exists()

    def test_scenarios_has_version(self, scenarios) -> None:
        assert "version" in scenarios

    def test_scenarios_has_categories(self, scenarios) -> None:
        cats = scenarios["categories"]
        assert "over-privilege" in cats
        assert "stale-access" in cats
        assert "data-plane" in cats

    def test_scenario_count(self, scenarios) -> None:
        assert len(scenarios["scenarios"]) >= 15

    def test_every_scenario_has_required_fields(self, scenarios) -> None:
        for s in scenarios["scenarios"]:
            assert "id" in s, f"Missing id in scenario: {s.get('title', '?')}"
            assert "title" in s
            assert "category" in s
            assert s["category"] in scenarios["categories"]
            assert "severity" in s
            assert s["severity"] in ("critical", "high", "medium", "low", "info")
            assert "terraform_source" in s

    def test_scenario_ids_unique(self, scenarios) -> None:
        ids = [s["id"] for s in scenarios["scenarios"]]
        assert len(ids) == len(set(ids))

    def test_terraform_sources_exist(self, scenarios) -> None:
        for s in scenarios["scenarios"]:
            tf_path = FAUX_ROOT / s["terraform_source"]
            assert tf_path.exists(), f"Terraform source not found: {s['terraform_source']}"

    def test_scenarios_md_references_json(self) -> None:
        md_text = (FAUX_ROOT / "SCENARIOS.md").read_text(encoding="utf-8")
        assert "scenarios.json" in md_text

    def test_scenarios_md_covers_critical(self) -> None:
        md_text = (FAUX_ROOT / "SCENARIOS.md").read_text(encoding="utf-8")
        assert "S01" in md_text
        assert "S02" in md_text
        assert "break-glass" in md_text.lower() or "break glass" in md_text.lower()
        assert "shadow admin" in md_text.lower()

    def test_scenarios_md_covers_all_ids(self, scenarios) -> None:
        md_text = (FAUX_ROOT / "SCENARIOS.md").read_text(encoding="utf-8")
        for s in scenarios["scenarios"]:
            assert s["id"] in md_text, f"Scenario {s['id']} not found in SCENARIOS.md"


# ═══════════════════════════════════════════════════════════════════════════
# 4. Cross-validation: fixture ↔ scenarios
# ═══════════════════════════════════════════════════════════════════════════


class TestCrossValidation:
    """Fixture data should contain the principals referenced by scenarios."""

    def test_break_glass_user_exists(self, fixture_data, scenarios) -> None:
        """S01 references User index 0."""
        users = fixture_data["users"]
        assert users[0]["key"] == "user-0"

    def test_shadow_admin_user_exists(self, fixture_data, scenarios) -> None:
        """S02 references User index 99."""
        users = fixture_data["users"]
        assert users[99]["key"] == "user-99"

    def test_stale_access_user_exists(self, fixture_data, scenarios) -> None:
        """S04 references User index 50."""
        users = fixture_data["users"]
        assert users[50]["key"] == "user-50"

    def test_scenario_groups_exist_in_fixture(self, fixture_data, scenarios) -> None:
        """Any group referenced in scenarios should exist in fixture."""
        group_names = set(fixture_data["groups"].keys())
        for s in scenarios["scenarios"]:
            principal = s.get("principal", {})
            if principal.get("type") == "Group" and "ref" in principal:
                assert principal["ref"] in group_names, (
                    f"Group {principal['ref']} from scenario {s['id']} not in fixture"
                )

    def test_decommissioned_subscription_exists(self, fixture_data) -> None:
        """S04 relies on the decommissioned subscription existing."""
        sub_names = {s["display_name"] for s in fixture_data["subscriptions"]}
        assert any("decommissioned" in n for n in sub_names)
