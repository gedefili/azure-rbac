# Portable Coding Policies & Conventions

> This document captures the coding standards, documentation policies, commit
> conventions, and agent operating rules used across the SanMar IaC ecosystem.
> It is designed to be portable — drop it into any new project and use it as
> a `copilot-instructions.md` or agent system prompt.

---

## Table of Contents

1. [File Headers](#1-file-headers)
2. [TypeScript Standards](#2-typescript-standards)
3. [Code Comments & Documentation](#3-code-comments--documentation)
4. [Security Conventions](#4-security-conventions)
5. [Commit & Check-in Process](#5-commit--check-in-process)
6. [Branch & Tag Naming](#6-branch--tag-naming)
7. [Terraform Standards](#7-terraform-standards)
8. [Testing Conventions](#8-testing-conventions)
9. [Logging Conventions](#9-logging-conventions)
10. [Error Handling Patterns](#10-error-handling-patterns)
11. [Import Ordering](#11-import-ordering)
12. [Documentation Lifecycle](#12-documentation-lifecycle)
13. [Release Process](#13-release-process)
14. [Agent Operating Policies](#14-agent-operating-policies)
15. [Confirmation Gates](#15-confirmation-gates)
16. [Naming Conventions Summary](#16-naming-conventions-summary)

---

## 1. File Headers

Every source file must include a structured header block. The format varies by
language but the **seven required fields** are always the same:

| Field | Description |
|---|---|
| `Repository` | Which repository the file belongs to |
| `Path` | Relative path within the repository |
| `Purpose` | One-line description of the file's role |
| `Author` | Creator — team name or `GitHub Copilot (<model>)` |
| `Created` | ISO date `YYYY-MM-DD` |
| `Last-Modified` | ISO date `YYYY-MM-DD` — update on every change |
| `Version` | Semantic version `X.Y.Z` |

### TypeScript (JSDoc block)

```typescript
/**
 * Repository: <repo-name>
 * Path: <relative-path>
 * Purpose: <one-liner>
 * Author: SanMar Platform Team
 * Created: 2026-01-14
 * Last-Modified: 2026-01-14
 * Version: 1.0.0
 */
```

### Bash / Shell (line comments, boxed)

```bash
#!/usr/bin/env bash
# =============================================================================
# Repository: <repo-name>
# Path: <relative-path>
# Purpose: <one-liner>
# Author: SanMar Platform Team
# Created: 2026-01-14
# Last-Modified: 2026-01-14
# Version: 1.0.0
# =============================================================================
```

A simpler unboxed variant using `#` line-comments is also acceptable.

### Markdown (HTML comment)

```html
<!--
Repository: <repo-name>
Path: <relative-path>
Purpose: <one-liner>
Author: <author>
Created: 2026-01-14
Last-Modified: 2026-01-14
Version: 0.1.0
-->
```

### Terraform (HCL block comment)

```hcl
# =============================================================================
# Repository: <repo-name>
# Path: <relative-path>
# Purpose: <one-liner>
# Author: <author>
# Created: 2026-01-14
# Last-Modified: 2026-01-14
# Version: 0.1.0
# =============================================================================
```

### Validation Rules

- `Path` must match the file's actual location.
- `Last-Modified` must be updated whenever the file is changed.
- `Version` must follow semver.

---

## 2. TypeScript Standards

### Compiler Configuration

| Setting | Value |
|---|---|
| `target` | ES2022 |
| `module` | NodeNext |
| `strict` | `true` |
| `noImplicitAny` | `true` |
| `strictNullChecks` | `true` |
| `noUnusedLocals` | `true` |
| `noUnusedParameters` | `true` |
| `noImplicitReturns` | `true` |
| `noFallthroughCasesInSwitch` | `true` |
| `declaration` | `true` |
| `sourceMap` | `true` |
| `isolatedModules` | `true` |

### Language Rules

- Prefer `const` over `let`; **never** use `var`.
- Use explicit return types on all exported functions.
- Use `async`/`await` — never raw `.then()` Promise chains.
- No `any` types; use explicit typing throughout.
- All async operations must be wrapped in `try`/`catch`.
- Remove unused variables, parameters, and imports.

---

## 3. Code Comments & Documentation

### JSDoc / TSDoc

Exported functions and classes should have full JSDoc with:

```typescript
/**
 * Brief description of what the function does.
 *
 * @param inputPath - The user-supplied path to validate
 * @param allowedPaths - Optional custom allowlist
 * @returns The resolved absolute path if valid
 * @throws Error if path is outside allowed directories
 *
 * @example
 * const safePath = validatePath("/workspaces/modules-iac/azure/compute");
 */
```

Required tags for non-trivial exports:
- `@param` — every parameter
- `@returns` — what the function returns
- `@throws` — error conditions
- `@example` — usage example where helpful

Lighter JSDoc (description only) is acceptable for simple internal helpers and
React component files.

File-level documentation uses `@file` and `@description`:

```typescript
/**
 * @file model-router.ts
 * @description Model routing logic for selecting optimal LLMs per task type
 */
```

### Section Separators

Use visual separators to organize code into logical sections:

**TypeScript:**

```typescript
// ============================================================================
// Section Name — brief description
// ============================================================================
```

**Alternative (Unicode box-drawing):**

```typescript
/* ── Section Name ───────────────────────────────────────────────────── */
```

**Bash:**

```bash
# =============================================================================
# Section Name
# =============================================================================
```

### Documentation Expectations

- **Document everything** — every exported symbol should have a JSDoc
  comment.
- Prefer inline comments that explain *why*, not *what*.
- Keep comments current — stale comments are worse than no comments.

---

## 4. Security Conventions

### Input Sanitization

All user-supplied input must be sanitized before use:

| Function | Purpose |
|---|---|
| `sanitizeArg()` | Reject shell metacharacters: `` ` $ " \ ; & | > < ( ) \n \r \0 `` |
| `sanitizeEnum()` | Validate against an explicit allowlist of values |
| `sanitizeNonFlag()` | Reject values starting with `-` (argument injection) |
| `sanitizeInput()` | Combines `sanitizeArg` + `sanitizeNonFlag` (recommended default) |

### CLI Execution

**Mandatory array-based spawn** — never use shell interpolation:

```typescript
// CORRECT
const proc = spawn(command, args, { shell: false });

// FORBIDDEN — never do this
exec(`${command} ${userInput}`);
spawn("bash", ["-c", `${command} ${userInput}`]);
```

### Path Validation

- All user-supplied paths must be validated against an allowlist of
  workspace directories.
- Paths must use a known prefix (e.g., `/workspaces/`).

### Web Application / Backend API Security

- **Parameter Validation & Allowlisting:** All API parameters sent by clients (e.g., model deployments, parameters) must be validated server-side against an explicit allowlist. Do not trust client payloads.
- **Authentication & Authorization:** All backend API routes must require authentication (e.g., Entra ID Bearer tokens) and appropriate RBAC checks.
- **Sandbox Infrastructure Execution:** Parsing and executing unverified infrastructure configs (e.g., Terraform HCL sent from client) must be performed in strictly isolated sandbox environments. Exclude dangerous providers (`local-exec`) to prevent unauthenticated Remote Code Execution.
- **Error Sanitization:** Never leak server-side file paths, stack traces, or raw CLI stderr to the frontend. Trap server faults and return localized, structured domain errors.

### Secrets

- Never hardcode tokens, passwords, or subscription IDs in code.
- Never include secrets in commit messages or logs.

---

## 5. Commit & Check-in Process

### Direct Commits to Main are Forbidden
**Zero direct commits to `main`.** All modifications must be made through the following strict workflow:
1.  **Branching**: Always create a feature branch (`git checkout -b <user>/<type>/<topic>`).
2.  **Pull Request**: Submit a Pull Request targeting `main`. Do not use direct `git push origin main`.
3.  **Merge**: Only merge (squash merge preferred) after the PR is created.

*If an AI agent or automated assistant is asked to manage code and merge into main, it must PROCEED via a PR. If it encounters permission or access issues executing PR creation via the CLI (like missing `gh` or `az` auth), the agent must STOP and ask the operator to manually authenticate, provide a PAT, or approve the PR. The process must never be bypassed to push directly to main.*

### Creating Pull Requests

The `az repos pr create` CLI command **does not work** in dev containers due to
credential-store issues.  Use one of these alternatives:

1. **`bin/azdo-pr`** — a bash script that calls the Azure DevOps REST API
   directly with `curl`.  It auto-detects the org, project, and repo from
   the git remote URL and reads `AZURE_DEVOPS_EXT_PAT` from `.env`.

   ```bash
   # Create PR with squash auto-complete (preferred):
   bin/azdo-pr -t "feat(scope): description" --squash

   # Create and immediately complete:
   bin/azdo-pr -t "fix(scope): description" --complete
   ```

2. **Direct REST API** — if `bin/azdo-pr` is not available, use `curl`:
   ```bash
   source .env
   curl -s -X POST \
     -u ":${AZURE_DEVOPS_EXT_PAT}" \
     -H "Content-Type: application/json" \
     -d '{"sourceRefName":"refs/heads/<branch>","targetRefName":"refs/heads/main","title":"<title>"}' \
     "https://dev.azure.com/sanmarcloud/<Project>/_apis/git/repositories/<repo>/pullrequests?api-version=7.1"
   ```

**Do NOT use `az repos pr create`** — it silently fails in dev containers.

### Step-by-Step Workflow for AI Agents

When asked to make changes and merge them, follow these steps exactly:

1. `git checkout -b <user>/<type>/<topic>` — create a feature branch.
2. Make changes, `git add`, `git commit` with a conventional commit message.
3. `git push origin <branch>` — push the feature branch only.
4. Run `bin/azdo-pr -t "<type>(<scope>): <message>" --squash` to create a PR.
5. If `bin/azdo-pr` is not present, use the REST API with `curl` as shown above.
6. If the PAT is missing or expired, **STOP** and ask the operator.
   Never fall back to `git push origin main`.
7. Report the PR URL to the user.

### Conventional Commits

All commits follow the **Conventional Commits** specification:

```
<type>(<scope>): <description>
```

### Allowed Types

| Type | Purpose |
|---|---|
| `feat` | New feature or capability |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `chore` | Maintenance, dependencies, config |
| `refactor` | Code restructuring (no behaviour change) |
| `test` | Adding or updating tests |
| `ci` | CI/CD pipeline changes |
| `perf` | Performance improvements |

### Commit Message Rules

- **Imperative mood** — "add feature" not "added feature"
- Lowercase first letter
- No period at the end
- Keep under 72 characters
- When in doubt, use `chore` as the type

### Scope

- Free-form, lowercase, no shell metacharacters
- Identifies the affected module, agent, or component
- Examples: `containers`, `networking`, `gitops-agent`, `mcp-common`

### Examples

```
feat(containers): add container app scaling configuration
fix(networking): correct subnet delegation for postgres
docs(gitops-agent): update README with branch naming rules
chore(deps): bump @sanmar/mcp-common to 1.3.0
refactor(scaffold-agent): extract template helpers to shared module
test(drift-agent): add unit tests for state comparison
ci(yaml-iac): add approval gate to production pipeline
perf(builder-agent): cache dependency graph between runs
```

### Pre-commit Checklist

Before committing:
- [ ] Code builds without errors
- [ ] Tests pass
- [ ] File headers are present and up to date
- [ ] No unused variables, imports, or parameters
- [ ] No secrets in code or commit message
- [ ] Documentation index is current if docs changed

---

## 6. Branch & Tag Naming

### Branches

```
<user>/<type>/<topic>
```

- `type` — same as commit types (feat, fix, docs, chore, refactor, test)
- `topic` — lowercase, hyphen-separated, alphanumeric only
- Example: `geoffdefilippi/feat/add-keyvault-module`

Topic is sanitized: uppercase → lowercase, spaces/underscores → hyphens,
non-alphanumeric characters removed.

### Tags

For module versions:

```
<module-key>/vX.Y.Z
```

Example: `azure.containers.container_app/v1.2.0`

Simple version tags: `vX.Y.Z`

---

## 7. Terraform Standards

### Naming

- All resource names, variables, and outputs use `snake_case`.

### Module Structure

Every module must contain:

```
module_name/
  main.tf          # Resources
  variables.tf     # Input variables
  outputs.tf       # Output values
  README.md        # Documentation
  VERSION          # Plain semver string (e.g., "0.1.0")
  CHANGELOG.md     # Keep-a-Changelog format
```

### Version Pinning

- Pin module versions explicitly — **never** use `ref=main`.
- Track pinned versions in `.module-pins.json`.

### Concern Markers

Security concerns are tagged with paired markers:

```hcl
#-^-# <concern-id>, <category>
... code ...
#-v-# <concern-id>, <category>
```

Rules:
- Markers must be properly paired (open/close).
- Concern blocks must not nest.
- IDs must match registry entries.

### Resource ID Normalization

When handling Azure resource IDs, always use a `resource_id_normalizer`
utility module — never inline ternary logic.

Values may be full IDs (`/subscriptions/xxx/resourceGroups/...`) or partial
IDs (`/resourceGroups/...` with the subscription auto-prefixed).

### Standard Variables

New modules should include these base variables:

```hcl
variable "name" { ... }
variable "resource_group_name" { ... }
variable "location" { ... }
variable "tags" { type = map(string), default = {} }
```

Sensitive variables should include `sensitive = true`.

---

## 8. Testing Conventions

### TypeScript (Backend / Agents)

Use the **Node.js built-in test runner** (`node:test` + `node:assert/strict`):

```typescript
import { describe, it } from "node:test";
import * as assert from "node:assert/strict";

describe("featureName", () => {
  it("should do the expected thing", () => {
    assert.strictEqual(actual, expected);
  });
});
```

### TypeScript (Frontend / React)

Use **Vitest**:

```typescript
import { describe, expect, test } from "vitest";
```

### Shell Smoke Tests

Simple `pass()`/`fail()` helper functions exercising CLI commands in temp
directories:

```bash
pass() { echo "PASS $1"; }
fail() { echo "FAIL $1"; exit 1; }
```

### General Rules

- Add or update tests whenever behavior changes.
- Tests must be reproducible — use temp directories and clean up.
- Organize tests with `describe` blocks and section separator comments.
- Verification evidence should be complete and documented.

---

## 9. Logging Conventions

### Bash Logging

Four levels with ISO 8601 UTC timestamps on `stdout`/`stderr`:

```
INFO  [2026-01-14T10:00:00Z] message     → stdout
WARN  [2026-01-14T10:00:00Z] message     → stderr
ERROR [2026-01-14T10:00:00Z] message     → stderr
DEBUG [2026-01-14T10:00:00Z] message     → conditional on LOG_LEVEL=debug
```

### TypeScript Logging

Log only to `stderr` when `stdout` is reserved for protocol output (e.g.,
MCP servers):

```typescript
function log(message: string): void {
  console.error(`[${new Date().toISOString()}] [agent-name] ${message}`);
}
```

Structured data logged as JSON:

```typescript
console.error(`[${timestamp}] [${name}] ${message}`, JSON.stringify(data));
```

---

## 10. Error Handling Patterns

### TypeScript

All async operations use `try`/`catch` with structured error results:

```typescript
try {
  const result = await performOperation();
  return { content: [{ type: "text", text: result }] };
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  return {
    content: [{ type: "text", text: `Error: ${message}` }],
    isError: true,
  };
}
```

- Surface CLI exit codes: `Error (exit ${code}): ${msg}`
- Provide clear, actionable error text — no stack traces exposed to users.
- Use `successResult()` and `errorResult()` helper methods when available.

### Bash

```bash
set -euo pipefail   # Strict mode in every script

error() { log_error "$1"; exit 1; }
require_arg() {
  local v="$1" name="$2"
  [[ -n "${v}" ]] || error "Missing required ${name}"
}
```

---

## 11. Import Ordering

### TypeScript (Backend / Agents)

1. SDK / framework imports (`@modelcontextprotocol/sdk/*`)
2. Node.js built-ins (`child_process`, `url`, `path`, `fs`)
3. Internal / shared imports (`@sanmar/mcp-common/*`)

### TypeScript (Frontend / React)

1. React imports (`react`, `react-dom`)
2. Local component imports
3. Local service/config imports
4. Type imports

---

## 12. Documentation Lifecycle

### README as the Canonical Index

- README is the root documentation index for every repository.
- Do not create competing top-level indexes.
- Every maintained document must have a README entry.
- No README link should target a missing file.

### Keeping Docs Current

- When code changes, update related documentation in the same commit.
- Flag stale commands, outdated assumptions, and obsolete sections.
- Prefer minimal edits that preserve intent.
- Docs should be actionable and checklist-oriented where applicable.

### Documentation Agent Workflow

1. **Index Agent** — keeps README links complete and valid. Adds missing
   links, removes stale links, normalizes labels.
2. **Refresh Agent** — reviews status accuracy, flags stale content, patches
   text to match reality.

### Generated Documentation

- Generated READMEs include a `> Generated by <tool>` notice.
- Generated docs include the standard HTML comment header.
- Module READMEs include sections: Overview, Inputs, Outputs, Usage.
- Index files are sorted alphabetically.

---

## 13. Release Process

### Pre-release

- Freeze feature merges for the release window.
- Verify README status and documentation index are current.
- Confirm documentation links are valid.

### Validation

- [ ] `npm test` passes
- [ ] `npm run build` succeeds
- [ ] Smoke test core flows in local dev
- [ ] Visual diffs/screenshots captured if UI changed

### Release

- Draft release notes from merged work using the standard template.
- Summarize user-visible changes, fixes, and known limitations.
- Include upgrade or migration notes.
- Create a version tag (`vX.Y.Z`).

### Release Notes Template

```markdown
# <project> vX.Y.Z

## Summary
One-paragraph summary of this release.

## Highlights
- Item 1

## Fixes
- Fix 1

## Documentation
- Documentation updates included in this release.
- README index and release docs verified.

## Known issues
- Issue 1

## Verification
- `npm test`
- `npm run build`

## Upgrade notes
Describe any setup, migration, or configuration changes needed.
```

### Post-release

- Re-open normal merge flow.
- Track hotfix issues and prioritize regressions.
- Announce to team/channel.
- Create follow-up issues for deferred work.

---

## 14. Agent Operating Policies

### Multi-Agent Workflow

Work is decomposed into streams: architecture, implementation, security, QA,
documentation, and design. The orchestrator assigns the minimal required set
of agents.

### Required Validation Gates

Every merged change must receive explicit consideration from:
1. **Architecture** — boundary and dependency direction check
2. **Coding** — implementation with tests
3. **Security** — threat surface, secrets, command execution review
4. **QA** — verification evidence (tests, build, smoke checks)
5. **Documentation** — index validity and content freshness

UI-facing changes additionally require at least one design/creative agent.

### Agent Rules

- Implement minimal, maintainable changes.
- Preserve existing style and patterns.
- Surface tradeoffs and handoff notes.
- Block completion when required validations are missing.

### MCP Interaction Rules

1. **Discover first** — list available resources before reading.
2. **Least-privilege context** — read only what the current subtask needs.
3. **Cite sources** — reference resource IDs/URIs in handoff notes.
4. **No silent mutation** — log all write operations.
5. **Fallback path** — continue with repository files if MCP is unavailable;
   record the gap.

---

## 15. Confirmation Gates

Destructive or remote write operations require an explicit `confirm` parameter
with a specific token string to prevent accidental execution:

| Operation | Required Token |
|---|---|
| Push after commit | `confirm='push'` |
| Push after tag | `confirm='push-tag'` |
| Create pull request | `confirm='create-pr'` |
| Delete remote branches | `confirm='delete-remote'` |

If the token is not provided or does not match, the operation fails with a
clear error message telling the user what token to provide.

---

## 16. Naming Conventions Summary

| Context | Convention | Example |
|---|---|---|
| Terraform resources | `snake_case` | `container_app_scaling` |
| Terraform variables | `snake_case` | `resource_group_name` |
| TypeScript variables | `camelCase` | `allowedPaths` |
| TypeScript exports | `camelCase` / `PascalCase` (classes) | `validatePath`, `AgentMcpServer` |
| MCP tool names | `snake_case` | `generate_readme` |
| CLI subcommands | `kebab-case` | `generate-readme` |
| Branch names | `<user>/<type>/<topic>` | `user/feat/add-module` |
| Commit messages | Conventional Commits | `feat(scope): description` |
| Tags | `<key>/vX.Y.Z` or `vX.Y.Z` | `module/v1.2.0` |
| File names (TS) | `kebab-case` | `model-router.ts` |
| File names (TF) | `snake_case` | `main.tf`, `variables.tf` |

---

## Code Review Checklist (Quick Reference)

### TypeScript
- [ ] No `any` types; explicit return types on exports
- [ ] `async`/`await` only — no `.then()` chains
- [ ] `const` preferred; no `var`
- [ ] All async ops in `try`/`catch`
- [ ] No unused variables, parameters, or imports
- [ ] File header present and current

### Security
- [ ] CLI calls use `spawn()` with `shell: false`
- [ ] User paths validated against allowlist
- [ ] Inputs pass through `sanitizeInput()`
- [ ] No hardcoded secrets
- [ ] Destructive ops require confirmation tokens

### Terraform
- [ ] `snake_case` for all names
- [ ] Module has `main.tf`, `variables.tf`, `outputs.tf`, `README.md`
- [ ] Versions pinned explicitly
- [ ] Resource IDs use normalizer module
- [ ] Concern markers properly paired
- [ ] Sensitive variables marked

### Documentation
- [ ] File header present with all 7 fields
- [ ] JSDoc on all exported symbols
- [ ] README index updated if docs changed
- [ ] No stale links in README
