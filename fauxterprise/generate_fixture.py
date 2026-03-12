#!/usr/bin/env python3
"""Generate a JSON fixture by parsing the Fauxterprise Terraform files.

**The Terraform is the single source of truth.**  This script reads every
``.tf`` file, extracts the data definitions (users, groups, subscriptions,
role assignments, etc.), and produces the exact JSON fixture that represents
what the Azure SDK would return after ``terraform apply``.

If you change the Terraform – add a user, rename a group, create a new role
assignment – the fixture changes automatically on the next run.

Usage::

    python fauxterprise/generate_fixture.py              # → fauxterprise/fixture.json
    python fauxterprise/generate_fixture.py -o custom.json
"""

from __future__ import annotations

import argparse
import json
import math
import uuid
from pathlib import Path

from terraform_parser import (
    RoleAssignmentDef,
    TerraformData,
    parse_fauxterprise,
)

# ---------------------------------------------------------------------------
# Deterministic UUID generator – seeded from a namespace so reruns are stable
# ---------------------------------------------------------------------------
NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


def _stable_id(name: str) -> str:
    """Return a deterministic UUID-5 for *name*."""
    return str(uuid.uuid5(NAMESPACE, name))


# ---------------------------------------------------------------------------
# Well-known role permission stubs (Azure platform constants, not in Terraform)
# ---------------------------------------------------------------------------
ROLE_PERMISSIONS: dict[str, dict] = {
    "Owner": {"actions": ["*"], "not_actions": [], "data_actions": [], "not_data_actions": []},
    "Contributor": {
        "actions": ["*"],
        "not_actions": [
            "Microsoft.Authorization/*/Delete",
            "Microsoft.Authorization/*/Write",
            "Microsoft.Authorization/elevateAccess/Action",
        ],
        "data_actions": [],
        "not_data_actions": [],
    },
    "Reader": {
        "actions": ["*/read"],
        "not_actions": [],
        "data_actions": [],
        "not_data_actions": [],
    },
    "User Access Administrator": {
        "actions": [
            "*/read",
            "Microsoft.Authorization/*",
            "Microsoft.Support/*",
        ],
        "not_actions": [],
        "data_actions": [],
        "not_data_actions": [],
    },
}


# ---------------------------------------------------------------------------
# Generators – each takes TerraformData and produces fixture sections
# ---------------------------------------------------------------------------


def _generate_users(tf: TerraformData) -> list[dict]:
    """Generate users using the same algorithm as Terraform's for-expression.

    Mirrors:
        for i in range(100) : {
          first_name = local.first_names[i % 20]
          last_name  = local.last_names[(floor(i / 20) + i % 20) % 20]
        }
    """
    n_first = len(tf.first_names)
    n_last = len(tf.last_names)
    n_deps = len(tf.departments)
    n_titles = len(tf.job_titles)
    count = n_first * (100 // n_first) if n_first else 100
    users = []
    for i in range(count):
        first = tf.first_names[i % n_first]
        last = tf.last_names[(math.floor(i / n_first) + i % n_first) % n_last]
        dept = tf.departments[i % n_deps] if n_deps else ""
        title = tf.job_titles[i % n_titles] if n_titles else ""
        upn = f"{first.lower()}.{last.lower()}.{i}@{tf.domain}"
        users.append({
            "key": f"user-{i}",
            "object_id": _stable_id(f"user-{i}"),
            "display_name": f"{first} {last}",
            "user_principal_name": upn,
            "department": dept,
            "job_title": title,
            "principal_type": "User",
            "enabled": True,
        })
    return users


def _generate_groups(tf: TerraformData) -> dict[str, dict]:
    return {
        name: {
            "object_id": _stable_id(f"group-{name}"),
            "display_name": f"{tf.prefix}-{name}",
            "description": attrs.get("description", ""),
            "principal_type": "Group",
        }
        for name, attrs in tf.groups.items()
    }


def _generate_group_memberships(
    tf: TerraformData, users: list[dict], groups: dict[str, dict],
) -> dict[str, list[str]]:
    """Apply the parsed membership rules to assign users to groups."""
    memberships: dict[str, list[str]] = {g: [] for g in groups}

    for u in users:
        idx = int(u["key"].split("-")[1])

        for rule in tf.membership_rules:
            if rule.rule_type == "dept":
                primary = tf.dept_to_group.get(u["department"])
                if primary and primary in memberships:
                    memberships[primary].append(u["object_id"])
            elif rule.rule_type == "modulo":
                if rule.modulo and idx % rule.modulo == (rule.remainder or 0):
                    if rule.group_ref in memberships:
                        memberships[rule.group_ref].append(u["object_id"])

    return memberships


def _generate_service_principals(tf: TerraformData) -> list[dict]:
    return [
        {
            "name": name,
            "object_id": _stable_id(f"sp-{name}"),
            "display_name": f"{tf.prefix}-sp-{name}",
            "principal_type": "ServicePrincipal",
        }
        for name in tf.service_principal_names
    ]


def _generate_management_groups(tf: TerraformData) -> list[dict]:
    key_to_display: dict[str, str] = {}
    for mg_def in tf.management_group_defs:
        dn = mg_def.display_name_tpl.replace("${var.prefix}", tf.prefix)
        key_to_display[mg_def.key] = dn

    mgs = []
    for mg_def in tf.management_group_defs:
        dn = key_to_display[mg_def.key]
        mg_id = f"/providers/Microsoft.Management/managementGroups/{dn}"
        parent_id = ""
        if mg_def.parent_key and mg_def.parent_key in key_to_display:
            parent_dn = key_to_display[mg_def.parent_key]
            parent_id = f"/providers/Microsoft.Management/managementGroups/{parent_dn}"
        mgs.append({
            "key": mg_def.key,
            "id": mg_id,
            "display_name": dn,
            "parent_id": parent_id,
        })
    return mgs


def _generate_subscriptions(tf: TerraformData) -> dict[str, dict]:
    subs: dict[str, dict] = {}
    for key, sub_def in tf.subscriptions.items():
        sub_id = _stable_id(f"sub-{key}")
        rg_names = {}
        rg_ids = {}
        for rg in sub_def["resource_groups"]:
            rg_name = f"{tf.prefix}-{key}-{rg}-rg"
            rg_id = f"/subscriptions/{sub_id}/resourceGroups/{rg_name}"
            rg_names[rg] = rg_name
            rg_ids[rg] = rg_id
        subs[key] = {
            "subscription_id": sub_id,
            "display_name": sub_def["display_name"],
            "location": sub_def["location"],
            "mg": sub_def["mg"],
            "state": "Enabled",
            "resource_groups": rg_names,
            "resource_group_ids": rg_ids,
        }
    return subs


def _generate_role_definitions(tf: TerraformData) -> list[dict]:
    """Build role definitions from the parsed ``locals.roles`` map."""
    role_names_used: set[str] = {ra.role_name for ra in tf.role_assignment_defs}
    snake_to_uuid = tf.role_definitions

    # Build display_name → UUID
    name_to_uuid: dict[str, str] = {}
    for snake_key, uid in snake_to_uuid.items():
        display_guess = snake_key.replace("_", " ").title()
        name_to_uuid[display_guess] = uid
    for role_name in role_names_used:
        if role_name not in name_to_uuid:
            snake = role_name.lower().replace(" ", "_")
            if snake in snake_to_uuid:
                name_to_uuid[role_name] = snake_to_uuid[snake]

    defs = []
    for role_name in sorted(role_names_used | set(name_to_uuid.keys())):
        uid = name_to_uuid.get(role_name)
        if not uid:
            snake = role_name.lower().replace(" ", "_")
            uid = snake_to_uuid.get(snake, _stable_id(f"role-{role_name}"))
        full_id = f"/providers/Microsoft.Authorization/roleDefinitions/{uid}"
        perms = ROLE_PERMISSIONS.get(role_name, {
            "actions": [], "not_actions": [], "data_actions": [], "not_data_actions": [],
        })
        defs.append({
            "id": full_id,
            "name": role_name,
            "role_type": "BuiltInRole",
            "description": f"Built-in {role_name} role",
            "permissions": [perms],
        })
    return defs


def _resolve_role_uuid(role_name: str, tf: TerraformData) -> str:
    snake = role_name.lower().replace(" ", "_")
    return tf.role_definitions.get(snake, _stable_id(f"role-{role_name}"))


def _resolve_scopes(
    ra_def: RoleAssignmentDef,
    subs: dict[str, dict],
    tf: TerraformData,
) -> list[str]:
    """Resolve the concrete scope strings for a role assignment definition."""

    if ra_def.scope_type == "iterator":
        if ra_def.for_each_type == "sub_rgs" and ra_def.for_each_sub:
            sub = subs.get(ra_def.for_each_sub)
            return list(sub["resource_group_ids"].values()) if sub else []
        elif ra_def.for_each_type == "all_storage":
            return [
                f"/subscriptions/{sub['subscription_id']}/resourceGroups/"
                f"{tf.prefix}-{sk}-shared-rg/providers/Microsoft.Storage/"
                f"storageAccounts/{tf.prefix}{sk.replace('_', '')}sa"
                for sk, sub in subs.items()
                if "shared" in sub["resource_groups"]
            ]
        elif ra_def.for_each_type == "all_keyvaults":
            return [
                f"/subscriptions/{sub['subscription_id']}/resourceGroups/"
                f"{tf.prefix}-{sk}-security-rg/providers/Microsoft.KeyVault/"
                f"vaults/{tf.prefix}-{sk}-kv"
                for sk, sub in subs.items()
                if "security" in sub["resource_groups"] or "shared" in sub["resource_groups"]
            ]
        return []

    if ra_def.scope_type == "specific_rg" and ra_def.scope_sub and ra_def.scope_rg:
        sub = subs.get(ra_def.scope_sub)
        if sub:
            rg_id = sub["resource_group_ids"].get(ra_def.scope_rg)
            return [rg_id] if rg_id else []
        return []

    if ra_def.scope_type == "first_rg" and ra_def.scope_sub:
        sub = subs.get(ra_def.scope_sub)
        if sub:
            rg_ids = list(sub["resource_group_ids"].values())
            return [rg_ids[0]] if rg_ids else []
        return []

    if ra_def.scope_type == "storage" and ra_def.scope_sub:
        sub = subs.get(ra_def.scope_sub)
        if sub:
            sk = ra_def.scope_sub
            return [
                f"/subscriptions/{sub['subscription_id']}/resourceGroups/"
                f"{tf.prefix}-{sk}-shared-rg/providers/Microsoft.Storage/"
                f"storageAccounts/{tf.prefix}{sk.replace('_', '')}sa"
            ]
        return []

    if ra_def.scope_type == "keyvault" and ra_def.scope_sub:
        sub = subs.get(ra_def.scope_sub)
        if sub:
            sk = ra_def.scope_sub
            return [
                f"/subscriptions/{sub['subscription_id']}/resourceGroups/"
                f"{tf.prefix}-{sk}-security-rg/providers/Microsoft.KeyVault/"
                f"vaults/{tf.prefix}-{sk}-kv"
            ]
        return []

    return []


def _generate_role_assignments(
    tf: TerraformData,
    users: list[dict],
    groups: dict[str, dict],
    subs: dict[str, dict],
) -> list[dict]:
    """Generate role assignments from parsed Terraform resource definitions."""
    assignments: list[dict] = []
    counter = 0
    user_keys = sorted(users, key=lambda u: int(u["key"].split("-")[1]))

    def _add(principal_id: str, principal_type: str, role_name: str, scope: str) -> None:
        nonlocal counter
        role_uuid = _resolve_role_uuid(role_name, tf)
        role_def_id = f"/providers/Microsoft.Authorization/roleDefinitions/{role_uuid}"
        ra_id = f"{scope}/providers/Microsoft.Authorization/roleAssignments/{_stable_id(f'ra-{counter}')}"
        assignments.append({
            "id": ra_id,
            "principal_id": principal_id,
            "principal_type": principal_type,
            "role_definition_id": role_def_id,
            "role_name": role_name,
            "scope": scope,
        })
        counter += 1

    for ra_def in tf.role_assignment_defs:
        # Determine principal(s)
        if ra_def.principal_type == "Group" and ra_def.group_ref:
            group_data = groups.get(ra_def.group_ref)
            if not group_data:
                continue
            principal_ids = [(group_data["object_id"], "Group")]
        elif ra_def.principal_type == "User" and ra_def.user_index is not None:
            if ra_def.user_index < len(user_keys):
                principal_ids = [(user_keys[ra_def.user_index]["object_id"], "User")]
            else:
                continue
        elif ra_def.principal_type == "Iterator" and ra_def.user_range:
            start, end = ra_def.user_range
            principal_ids = [
                (user_keys[i]["object_id"], "User")
                for i in range(start, min(end, len(user_keys)))
            ]
        else:
            continue

        # Determine scope(s)
        scopes = _resolve_scopes(ra_def, subs, tf)

        # Emit assignments (principals × scopes)
        for pid, ptype in principal_ids:
            for scope in scopes:
                _add(pid, ptype, ra_def.role_name, scope)

    return assignments


# ---------------------------------------------------------------------------
# Assemble fixture
# ---------------------------------------------------------------------------


def generate_fixture(tf_root: Path | str | None = None) -> dict:
    """Build the complete fixture by parsing Terraform as the single source of truth.

    Parameters
    ----------
    tf_root
        Path to the ``fauxterprise/`` Terraform directory.  Defaults to the
        directory containing this script.
    """
    if tf_root is None:
        tf_root = Path(__file__).parent
    tf_root = Path(tf_root)

    tf = parse_fauxterprise(tf_root)

    users = _generate_users(tf)
    groups = _generate_groups(tf)
    memberships = _generate_group_memberships(tf, users, groups)
    sps = _generate_service_principals(tf)
    mgs = _generate_management_groups(tf)
    subs = _generate_subscriptions(tf)
    role_defs = _generate_role_definitions(tf)
    role_assignments = _generate_role_assignments(tf, users, groups, subs)

    assignments_by_sub: dict[str, list[dict]] = {}
    for sub_data in subs.values():
        sub_id = sub_data["subscription_id"]
        assignments_by_sub[sub_id] = [
            ra for ra in role_assignments
            if f"/subscriptions/{sub_id}" in ra["scope"]
        ]

    resource_groups_by_sub: dict[str, list[dict]] = {}
    for sub_data in subs.values():
        sub_id = sub_data["subscription_id"]
        resource_groups_by_sub[sub_id] = [
            {"name": rg_name, "location": sub_data["location"]}
            for rg_name in sub_data["resource_groups"].values()
        ]

    tenant_id = _stable_id("tenant")

    return {
        "_meta": {
            "generator": "fauxterprise/generate_fixture.py",
            "source": "fauxterprise/*.tf (parsed with python-hcl2)",
            "description": "Simulated Azure tenant derived from Fauxterprise Terraform config",
            "tenant_id": tenant_id,
            "prefix": tf.prefix,
            "domain": tf.domain,
        },
        "tenant_id": tenant_id,
        "management_groups": mgs,
        "subscriptions": [
            {
                "subscription_id": sub["subscription_id"],
                "display_name": sub["display_name"],
                "state": sub["state"],
            }
            for sub in subs.values()
        ],
        "subscription_details": subs,
        "users": users,
        "groups": {
            name: {**data, "members": memberships.get(name, [])}
            for name, data in groups.items()
        },
        "service_principals": sps,
        "role_definitions": role_defs,
        "role_assignments": role_assignments,
        "role_assignments_by_subscription": assignments_by_sub,
        "resource_groups_by_subscription": resource_groups_by_sub,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Fauxterprise Azure fixture from Terraform")
    parser.add_argument(
        "-o", "--output",
        default=str(Path(__file__).parent / "fixture.json"),
        help="Output path (default: fauxterprise/fixture.json)",
    )
    parser.add_argument(
        "--tf-root",
        default=str(Path(__file__).parent),
        help="Path to fauxterprise/ Terraform directory",
    )
    args = parser.parse_args()

    fixture = generate_fixture(args.tf_root)
    Path(args.output).write_text(json.dumps(fixture, indent=2), encoding="utf-8")

    print(f"Fixture written to {args.output}")
    print(f"  Source:               {args.tf_root}/*.tf (parsed)")
    print(f"  Tenant:               {fixture['tenant_id']}")
    print(f"  Management groups:    {len(fixture['management_groups'])}")
    print(f"  Subscriptions:        {len(fixture['subscriptions'])}")
    print(f"  Users:                {len(fixture['users'])}")
    print(f"  Groups:               {len(fixture['groups'])}")
    print(f"  Service principals:   {len(fixture['service_principals'])}")
    print(f"  Role definitions:     {len(fixture['role_definitions'])}")
    print(f"  Role assignments:     {len(fixture['role_assignments'])}")


if __name__ == "__main__":
    main()
