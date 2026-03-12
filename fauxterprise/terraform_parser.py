"""Parse Fauxterprise Terraform files into structured data for fixture generation.

This module reads .tf files directly using python-hcl2, ensuring the generated
fixture always reflects the current Terraform configuration.  If you change the
Terraform – add a user, rename a group, create a role assignment – the fixture
changes automatically on the next generation run.

The parsed data feeds into ``generate_fixture.py`` which produces the JSON
fixture consumed by :class:`~azure_rbac.mock_client.MockAzureClient`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import hcl2

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Parsed data structures
# ---------------------------------------------------------------------------


@dataclass
class ManagementGroupDef:
    """A management group resource parsed from Terraform."""

    key: str
    display_name_tpl: str  # may contain ${var.prefix}
    parent_key: str | None = None  # key of the parent MG resource


@dataclass
class GroupMembershipRule:
    """A group-membership rule parsed from ``azuread_group_member`` resources."""

    resource_name: str
    group_ref: str  # group name extracted from group_object_id
    rule_type: str  # "dept" | "modulo"
    modulo: int | None = None
    remainder: int | None = None


@dataclass
class RoleAssignmentDef:
    """A role assignment resource parsed from Terraform."""

    resource_name: str
    role_name: str

    # Principal - one of:
    principal_type: str  # "Group", "User", "Iterator"
    group_ref: str | None = None  # group name for Group type
    user_index: int | None = None  # user index for User type

    # Scope pattern
    scope_type: str = "unknown"  # "iterator", "sub_rgs", "specific_rg", "first_rg", "storage", "keyvault"
    scope_sub: str | None = None  # subscription key
    scope_rg: str | None = None  # specific RG name within subscription

    # For-each pattern
    for_each_type: str = "none"  # "none", "sub_rgs", "all_storage", "all_keyvaults", "user_range"
    for_each_sub: str | None = None  # subscription key for sub_rgs
    user_range: tuple[int, int] | None = None  # (start, end) for user_range


@dataclass
class TerraformData:
    """All data extracted from the Fauxterprise Terraform files."""

    # Variables
    prefix: str = "faux"
    domain: str = "fauxterprise.onmicrosoft.com"

    # Identity data (from modules/identity/main.tf locals)
    first_names: list[str] = field(default_factory=list)
    last_names: list[str] = field(default_factory=list)
    departments: list[str] = field(default_factory=list)
    job_titles: list[str] = field(default_factory=list)
    groups: dict[str, dict[str, str]] = field(default_factory=dict)
    dept_to_group: dict[str, str] = field(default_factory=dict)
    service_principal_names: list[str] = field(default_factory=list)
    membership_rules: list[GroupMembershipRule] = field(default_factory=list)

    # Management groups (from modules/management-groups/main.tf)
    management_group_defs: list[ManagementGroupDef] = field(default_factory=list)

    # Subscriptions (from modules/subscriptions/main.tf locals)
    subscriptions: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Role definitions (from modules/role-assignments/main.tf locals)
    role_definitions: dict[str, str] = field(default_factory=dict)

    # Role assignments (from modules/role-assignments/main.tf resources)
    role_assignment_defs: list[RoleAssignmentDef] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Expression helpers
# ---------------------------------------------------------------------------

_EXPR_RE = re.compile(r"^\$\{(.+)\}$", re.DOTALL)


def _unwrap(s: Any) -> str:
    """Strip ``${…}`` wrapper that hcl2 adds around Terraform expressions."""
    if not isinstance(s, str):
        return str(s)
    m = _EXPR_RE.match(s)
    return m.group(1) if m else s


def _resolve_prefix(template: str, prefix: str) -> str:
    """Replace ``${var.prefix}`` interpolation with the actual prefix value."""
    return template.replace("${var.prefix}", prefix)


# ---------------------------------------------------------------------------
# HCL file helpers
# ---------------------------------------------------------------------------


def _parse_file(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return hcl2.load(fh)


def _collect_locals(parsed: dict) -> dict[str, Any]:
    """Merge all ``locals {}`` blocks into a single dict."""
    out: dict[str, Any] = {}
    for block in parsed.get("locals", []):
        out.update(block)
    return out


def _collect_resources(parsed: dict) -> dict[str, dict[str, dict]]:
    """Return ``{resource_type: {name: attrs}}`` from all resource blocks."""
    out: dict[str, dict[str, dict]] = {}
    for block in parsed.get("resource", []):
        for rtype, instances in block.items():
            out.setdefault(rtype, {}).update(instances)
    return out


def _collect_variable_defaults(parsed: dict) -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    for block in parsed.get("variable", []):
        for name, attrs in block.items():
            if "default" in attrs:
                defaults[name] = attrs["default"]
    return defaults


# ---------------------------------------------------------------------------
# Module-specific parsers
# ---------------------------------------------------------------------------


def _parse_variables(root: Path) -> dict[str, Any]:
    """Read top-level ``variables.tf`` defaults."""
    path = root / "variables.tf"
    if not path.exists():
        return {}
    parsed = _parse_file(path)
    return _collect_variable_defaults(parsed)


def _parse_identity(root: Path) -> dict[str, Any]:
    """Parse ``modules/identity/main.tf`` for users, groups, SPs."""
    path = root / "modules" / "identity" / "main.tf"
    parsed = _parse_file(path)
    lcls = _collect_locals(parsed)
    resources = _collect_resources(parsed)

    # Simple data
    result: dict[str, Any] = {
        "first_names": lcls.get("first_names", []),
        "last_names": lcls.get("last_names", []),
        "departments": lcls.get("departments", []),
        "job_titles": lcls.get("job_titles", []),
        "groups": lcls.get("groups", {}),
        "dept_to_group": lcls.get("dept_to_group", {}),
    }

    # Service principals – extract names from azuread_application for_each
    sp_names: list[str] = []
    app_res = resources.get("azuread_application", {})
    for _name, attrs in app_res.items():
        fe = _unwrap(attrs.get("for_each", ""))
        # Pattern: toset([name1, name2, ...])
        m = re.search(r"toset\(\[(.+?)\]\)", fe)
        if m:
            names_str = m.group(1)
            sp_names = [n.strip().strip('"').strip("'") for n in names_str.split(",")]
    result["service_principal_names"] = sp_names

    # Group membership rules
    rules: list[GroupMembershipRule] = []
    gm_resources = resources.get("azuread_group_member", {})
    for res_name, attrs in gm_resources.items():
        group_oid = _unwrap(attrs.get("group_object_id", ""))
        fe = _unwrap(attrs.get("for_each", ""))

        if res_name == "primary":
            # Department-based: all users, group from dept_to_group
            rules.append(GroupMembershipRule(
                resource_name=res_name,
                group_ref="__dept__",
                rule_type="dept",
            ))
        else:
            # Modulo-based: extract group name and modulo/remainder
            grp_match = re.search(r'groups\["([\w-]+)"\]', group_oid)
            group_name = grp_match.group(1) if grp_match else res_name

            # Extract modulo condition: % N == M
            mod_match = re.search(r"%\s*(\d+)\s*==\s*(\d+)", fe)
            if mod_match:
                rules.append(GroupMembershipRule(
                    resource_name=res_name,
                    group_ref=group_name,
                    rule_type="modulo",
                    modulo=int(mod_match.group(1)),
                    remainder=int(mod_match.group(2)),
                ))
            else:
                logger.warning("Unrecognised membership rule: %s", res_name)

    result["membership_rules"] = rules
    return result


def _parse_management_groups(root: Path) -> list[ManagementGroupDef]:
    """Parse ``modules/management-groups/main.tf`` for MG hierarchy."""
    path = root / "modules" / "management-groups" / "main.tf"
    parsed = _parse_file(path)
    resources = _collect_resources(parsed)
    mg_resources = resources.get("azurerm_management_group", {})

    defs: list[ManagementGroupDef] = []
    for res_name, attrs in mg_resources.items():
        display_name = attrs.get("display_name", "")
        parent_ref = _unwrap(attrs.get("parent_management_group_id", ""))

        parent_key = None
        if parent_ref:
            # Pattern: azurerm_management_group.KEY.id
            m = re.search(r"azurerm_management_group\.(\w+)\.id", parent_ref)
            if m:
                parent_key = m.group(1)

        defs.append(ManagementGroupDef(
            key=res_name,
            display_name_tpl=display_name,
            parent_key=parent_key,
        ))

    return defs


def _parse_subscriptions(root: Path, prefix: str) -> dict[str, dict[str, Any]]:
    """Parse ``modules/subscriptions/main.tf`` for subscription definitions."""
    path = root / "modules" / "subscriptions" / "main.tf"
    parsed = _parse_file(path)
    lcls = _collect_locals(parsed)

    raw_subs = lcls.get("subscriptions", {})
    subs: dict[str, dict[str, Any]] = {}
    for key, attrs in raw_subs.items():
        subs[key] = {
            "display_name": _resolve_prefix(attrs.get("display_name", ""), prefix),
            "mg": attrs.get("mg", ""),
            "location": attrs.get("location", ""),
            "resource_groups": attrs.get("resource_groups", []),
        }
    return subs


def _parse_role_assignments(root: Path) -> tuple[dict[str, str], list[RoleAssignmentDef]]:
    """Parse ``modules/role-assignments/main.tf`` for role IDs and assignments."""
    path = root / "modules" / "role-assignments" / "main.tf"
    parsed = _parse_file(path)
    lcls = _collect_locals(parsed)
    resources = _collect_resources(parsed)

    # Role definition UUIDs
    role_defs: dict[str, str] = lcls.get("roles", {})

    # Role assignment resources
    ra_resources = resources.get("azurerm_role_assignment", {})
    defs: list[RoleAssignmentDef] = []

    for res_name, attrs in ra_resources.items():
        role_name = attrs.get("role_definition_name", "")
        pid_raw = _unwrap(attrs.get("principal_id", ""))
        scope_raw = _unwrap(attrs.get("scope", ""))
        fe_raw = _unwrap(attrs.get("for_each", "")) if "for_each" in attrs else None

        # --- Parse principal ---
        principal_type, group_ref, user_index = "Unknown", None, None

        grp_m = re.search(r'var\.groups\["([\w-]+)"\]', pid_raw)
        usr_m = re.search(r'var\.users\[local\.user_keys\[(\d+)\]\]', pid_raw)
        if grp_m:
            principal_type = "Group"
            group_ref = grp_m.group(1)
        elif usr_m:
            principal_type = "User"
            user_index = int(usr_m.group(1))
        elif pid_raw == "each.value":
            principal_type = "Iterator"
        else:
            logger.warning("Unknown principal: %s in %s", pid_raw, res_name)

        # --- Parse for_each ---
        fe_type, fe_sub, user_range = "none", None, None
        if fe_raw:
            sub_rgs_m = re.search(r'var\.subscriptions\["(\w+)"\]\.resource_group_ids', fe_raw)
            range_m = re.search(r"range\((\d+)\s*,\s*(\d+)\)", fe_raw)
            if sub_rgs_m:
                fe_type = "sub_rgs"
                fe_sub = sub_rgs_m.group(1)
            elif fe_raw == "var.storage":
                fe_type = "all_storage"
            elif fe_raw == "var.keyvaults":
                fe_type = "all_keyvaults"
            elif range_m:
                fe_type = "user_range"
                user_range = (int(range_m.group(1)), int(range_m.group(2)))
            else:
                logger.warning("Unknown for_each: %s in %s", fe_raw, res_name)

        # --- Parse scope ---
        scope_type, scope_sub, scope_rg = "unknown", None, None
        if scope_raw == "each.value":
            scope_type = "iterator"
        else:
            # var.subscriptions["key"].resource_group_ids["rg"]
            specific_m = re.search(
                r'var\.subscriptions\["(\w+)"\]\.resource_group_ids\["([\w-]+)"\]',
                scope_raw,
            )
            # values(var.subscriptions["key"].resource_group_ids)[N]
            first_m = re.search(
                r'values\(var\.subscriptions\["(\w+)"\]\.resource_group_ids\)',
                scope_raw,
            )
            storage_m = re.search(r'var\.storage\["(\w+)"\]', scope_raw)
            kv_m = re.search(r'var\.keyvaults\["(\w+)"\]', scope_raw)

            if specific_m:
                scope_type = "specific_rg"
                scope_sub = specific_m.group(1)
                scope_rg = specific_m.group(2)
            elif first_m:
                scope_type = "first_rg"
                scope_sub = first_m.group(1)
            elif storage_m:
                scope_type = "storage"
                scope_sub = storage_m.group(1)
            elif kv_m:
                scope_type = "keyvault"
                scope_sub = kv_m.group(1)

        defs.append(RoleAssignmentDef(
            resource_name=res_name,
            role_name=role_name,
            principal_type=principal_type,
            group_ref=group_ref,
            user_index=user_index,
            scope_type=scope_type,
            scope_sub=scope_sub,
            scope_rg=scope_rg,
            for_each_type=fe_type,
            for_each_sub=fe_sub,
            user_range=user_range,
        ))

    return role_defs, defs


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def parse_fauxterprise(root: Path | str) -> TerraformData:
    """Parse all Fauxterprise .tf files and return structured data.

    Parameters
    ----------
    root:
        Path to the ``fauxterprise/`` directory containing ``main.tf``,
        ``variables.tf``, and the ``modules/`` tree.

    Returns
    -------
    TerraformData
        A structured object whose fields are derived entirely from the
        Terraform source files.  Changing a ``.tf`` file and re-running
        the parser will reflect the change.
    """
    root = Path(root)
    data = TerraformData()

    # 1. Variables
    var_defaults = _parse_variables(root)
    data.prefix = var_defaults.get("prefix", data.prefix)
    data.domain = var_defaults.get("domain", data.domain)

    # 2. Identity (users, groups, SPs)
    identity = _parse_identity(root)
    data.first_names = identity["first_names"]
    data.last_names = identity["last_names"]
    data.departments = identity["departments"]
    data.job_titles = identity["job_titles"]
    data.groups = identity["groups"]
    data.dept_to_group = identity["dept_to_group"]
    data.service_principal_names = identity["service_principal_names"]
    data.membership_rules = identity["membership_rules"]

    # 3. Management groups
    data.management_group_defs = _parse_management_groups(root)

    # 4. Subscriptions
    data.subscriptions = _parse_subscriptions(root, data.prefix)

    # 5. Role assignments & definitions
    data.role_definitions, data.role_assignment_defs = _parse_role_assignments(root)

    logger.info(
        "Parsed Terraform: %d first_names, %d groups, %d subs, %d MGs, %d role_assignments",
        len(data.first_names),
        len(data.groups),
        len(data.subscriptions),
        len(data.management_group_defs),
        len(data.role_assignment_defs),
    )
    return data
