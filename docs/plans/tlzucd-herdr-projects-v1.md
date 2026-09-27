# Plan — herdr-projects v1

| | |
|---|---|
| **Status** | draft |
| **Updated** | 2026-09-26 |
| **Tracker** | — |
| **Related** | [design spec](../superpowers/specs/2026-09-26-herdr-projects-design.md), [herdr-launchpad](https://github.com/wmxscott/herdr-launchpad), [herdr-wkt](https://github.com/wmxscott/herdr-wkt), [#1](https://github.com/wmxscott/herdr-projects/pull/1) |

## Goal

Workspace labels of the form `<icon> <group>/<name>` become derived from a curated
registry instead of typed by hand: a herdr user can open a registered project as a
correctly labelled workspace from one popup, and any workspace sitting in a registered
location gets — or can be reset to — that project's label.

### Done when

- [ ] `herdr plugin install wmxscott/herdr-projects` succeeds on macOS against herdr ≥ 0.9.1.
- [ ] In a live herdr session, picking a registered project in the popup creates a
      workspace whose cwd is the project path and whose label is its registry label;
      picking it again focuses that workspace instead of creating a second one.
- [ ] `cd` into a registered project's subfolder, run the `rename` action: the
      workspace label changes to the project's label and a toast confirms it.
- [ ] A workspace created in a registered path — both via `herdr workspace create --cwd`
      and via herdr's own UI — is relabelled automatically, and a manual rename made
      afterwards survives switching away and back.
- [ ] A linked worktree workspace (from `wkt new`) inside a registered repo is never
      relabelled.
- [ ] A project can be added, edited (including a new group and an icon from the glyph
      picker) and deleted from the popup, and `projects.toml` stays a symlink when stowed.
- [ ] CI (lint, tests on macOS + Linux, manifest) is green and required on `main`.

## Settled — do not re-derive

**S1 — Curated registry, no discovery.** Projects enter only by explicit add. Rejected:
scanning roots like `~/Developer` (buries the used projects under backups and scratch
dirs) and scan-then-accept import (not wanted).

**S2 — Location identity, not git remote.** Open needs a path anyway; several projects
have no remote (`dotfiles-private`, `dotcom`, `swb/kb` have no worktree info in
`herdr workspace list`); a remote is shared by every `wkt` worktree and by monorepo
subfolders. Rejected: remote as primary or fallback key.

**S3 — Worktrees are out of scope.** herdr-wkt owns them. Linked worktrees are never
matched, renamed, or suffixed. An earlier draft suffixed worktree labels with
` · <branch>`; dropped by the user.

**S4 — Groups are explicit and keyed by `name`.** No separate group `id` (user: redundant).
Projects reference a group by its name.

**S5 — No color.** herdr labels are plain strings; `workspace.create`/`rename` have no
style field. The only styling is `ui.sidebar.*` token styles in the user's
`config.toml`, fixed per token (`fg`, `bold`, `dim`) — known from `herdr --default-config`
and `herdr api schema --json` (`WorkspaceReportMetadataParams.tokens` is string-only).
A per-color-token workaround exists; rejected by the user.

**S6 — Single herdr plugin, Python ≥ 3.11 stdlib + fzf.** Mirrors herdr-launchpad.
Rejected: standalone CLI + thin plugin (two things to version, duplicates herdr-wkt's
shape); a mode inside launchpad (mixes concerns).

**S7 — Picker is fzf with a chained icon sub-picker.** Rejected: plain fzf with icons
pasted into TOML (painful); a Textual TUI (dependency and maintenance cost).

**S8 — Auto-label only on creation.** Rename runs once per workspace, never on every
focus/cwd change, so manual relabels are never overwritten. Rejected: continuous sync.

**S9 — herdr facts (0.9.1, protocol 22).**
- `herdr workspace create --cwd P --label L --focus`, `workspace rename ID LABEL…`,
  `workspace list|get`, `workspace focus ID`, `pane current|get` all print
  `{"result": …}` JSON.
- `workspace list` entries carry `worktree.{checkout_path, is_linked_worktree, repo_root}`
  only for git checkouts.
- Plugin processes get `HERDR_PLUGIN_ROOT`, `HERDR_PLUGIN_STATE_DIR`,
  `HERDR_PLUGIN_CONFIG_DIR`, `HERDR_PLUGIN_CONTEXT_JSON` (has `focused_pane_id`),
  `HERDR_PLUGIN_EVENT`, `HERDR_PLUGIN_EVENT_JSON`.
- Event JSON wraps records under `data`; the workspace id is at
  `data.workspace.workspace_id`, `data.workspace.id`, or `data.workspace_id` depending on
  the event (from herdr-plugin-workspace-manager `src/apply_core.rs`).
- A popup keeps herdr's plugin context on the tiled pane beneath it, so
  `focused_pane_id` from the context is the user's pane even inside the popup
  (herdr-launchpad `agent_session`). Use it, not `herdr pane current`.
- Popups open with `herdr plugin pane open --plugin ID --entrypoint E --placement popup
  --width W --height H --focus [--env K=V]`; only one popup at a time ("popup already
  open" → retry).
- Toasts: `herdr notification show <title> --body <text>`.

**S10 — `workspace.created` may not fire for UI-created workspaces.** Reported by
herdr-plugin-workspace-manager's manifest comments; unverified on 0.9.1. Verified in A1
(see A1), resolved in A4.
*Resolved in A1 (2026-09-26): it does fire.* `herdr workspace create` was observed in
`hook.log`, and in herdr v0.9.1's source the UI `new_workspace` (and new-worktree) path
sends the same `WorkspaceCreate` request, reaching the same `emit_workspace_open_events`
(`src/app/creation.rs`). The root pane and its cwd exist when the event fires. Only
herdr's startup/default workspaces skip it. So A4 subscribes to `workspace.created` only.

**S11 — The launch shim runs `python -I -S`.** `-I` drops the script dir from `sys.path`,
so the entry must insert `lib/` itself. Shim is copied from herdr-launchpad
`bin/launchpad` (cached interpreter lookup in `$HERDR_PLUGIN_STATE_DIR/python`).

**S12 — No TOML writer in stdlib.** A small serializer for the flat schema; comments in
`projects.toml` are not preserved by picker edits. Accepted by the user.

## Registry contract

### File

`$HERDR_PLUGIN_CONFIG_DIR/projects.toml` (≡ `herdr plugin config-dir herdr-projects`).
Missing file = empty registry. May be a symlink.

```toml
[[groups]]
name = "swb"          # required, unique; label prefix
icon = ""            # optional; default icon for its projects

[[projects]]
name = "edge"         # required
group = "swb"         # optional; must name a group
icon = ""            # optional if its group has an icon
path = "~/Developer/switchbit-dev/edge"   # required; ~ expanded
```

### Validation

Errors (collect all, report with `groups[i]`/`projects[i]` locations):

- unknown key; wrong type; missing required key; empty string
- duplicate group name; project `group` not found
- project with no icon after group fallback
- duplicate label (ignoring icon); duplicate resolved path
- `path` not absolute after `~` expansion (amended in A2: a plugin's cwd is its root, so
  relative paths have no meaning)

A path that doesn't exist is **not** an error.

### Label

`<icon> <group>/<name>` when grouped, else `<icon> <name>`. Project icon overrides group
icon. The "bare label" is the same without the icon.

### Save

Serialize groups (sorted by name) then projects (sorted by group, name), keys in schema
order, strings escaped per TOML basic-string rules, paths re-collapsed to `~`. Write to
`realpath(file)`: temp file in the same directory, `fsync`, `os.replace`. Round-trip
(`parse(serialize(r)) == r`) must hold.

## Resolution contract

### Location → project

1. Location is inside a linked worktree → no match. Prefer herdr's
   `worktree.is_linked_worktree` when the workspace record has it; else
   `git -C <loc> rev-parse --path-format=absolute --git-dir --git-common-dir` and
   compare. Non-git dirs are not worktrees.
2. `realpath` location and every project path; the project whose path equals or is an
   ancestor of the location, with the longest path, wins.
3. Else no match.

### Location sources

| Caller | Location |
|---|---|
| `rename` (action, picker `ctrl-r`, CLI) | cwd of `focused_pane_id` from `HERDR_PLUGIN_CONTEXT_JSON`; CLI outside a plugin falls back to `herdr pane current` |
| `add` | same as rename |
| event hook | cwd of the new workspace's first pane (via `workspace get` → active tab → pane) |
| "already open" | each workspace's active pane cwd |

### Already open

Workspace W is the open instance of project P when W is not a linked worktree and its
location resolves to P. First in herdr's workspace order wins. "Active" = that workspace
is `focused`.

## Commands

### CLI surface

```
herdr-projects list                        # TSV: bare-label, path, status(open|active|missing|-)
herdr-projects open <group/name|name>      # bare name must be unambiguous
herdr-projects rename [--workspace ID]
herdr-projects add [PATH] [--name N] [--group G] [--icon I]
herdr-projects picker [--add]              # popup entrypoint
herdr-projects popup [--add]               # action entrypoint: opens the picker popup
herdr-projects event                       # event entrypoint
herdr-projects --version | --help
```

Exit codes: `0` ok, `1` user-facing failure (message on stderr, and a toast when running
under herdr), `2` usage error.

### Open

Resolve target → if open instance exists, `workspace focus`; else if path missing, fail;
else `workspace create --cwd <realpath> --label <label> --focus`.

### Rename

Resolve location → no match: fail with `No project for <location>` → label equal: no-op,
toast `Already <label>` → else `workspace rename`, toast `Renamed to <label>`.

### Add

Non-interactive with flags; `--name` defaults to basename. If the resolved path is already
registered, fail with `Already registered as <label>` (the picker turns this into edit).
New group via `--group` must already exist in the CLI; the picker creates groups.

### Event hook

Read workspace id from `HERDR_PLUGIN_EVENT_JSON` (S9), then run Rename for that workspace,
silently (no toast; no match is a no-op). Always exit 0; append errors to
`$HERDR_PLUGIN_STATE_DIR/hook.log`. Subscribes to `workspace.created` only (S10).

*Amended in A4: no `seen.json`.* It existed only to keep a `workspace.focused` path cheap,
which S10's resolution removed. It would also be wrong: herdr reuses workspace ids after a
session restore (`herdr-server.log`: `wE` created 2026-07-23 and again 2026-08-15, right
after a restore; likewise `wJ`, `wK`, `wN`, `wS`, `w11`–`w16`), so an id-keyed dedupe
would skip new workspaces. Restores emit no `workspace.created`, so S8 holds without it.

## Picker contract

### Main list

Popup `picker` entrypoint, width 70%, height 60%. Rows sorted by group then name:
`<icon>  <bare label>  <~path>  <status>`, status glyph U+F444 active, U+F4C3 open,
U+F0338 missing, blank otherwise. The action precomputes rows and passes them to the popup
via `--env`/a temp file in the state dir, as launchpad does, so the popup only starts fzf.

| Key | Effect |
|---|---|
| `enter` | Open |
| `ctrl-r` | Rename current workspace, close |
| `ctrl-a` | Add flow for current location |
| `ctrl-e` | Edit flow for selected |
| `ctrl-d` | `Delete <label>? [y/N]`, then save and reload list |
| `ctrl-o` | `$EDITOR projects.toml` (fallback `vi`), then reload |
| `esc` | Close |

Registry invalid → one row with the first error; only `ctrl-o` and `esc` act.
`fzf` missing → print the requirement, wait for a key, exit 1.

### Add / edit flow

1. Name — prompt with default (basename or current).
2. Group — fzf: existing group names, `none`, `+ new group` → prompt name, then Icon
   picker for the group icon (skippable).
3. Icon — Icon picker; first row `use group icon` when the group has one.

Esc at any step discards everything. Add on a registered path becomes edit. Save, then
return to the main list.

### Icon picker

fzf over `lib/herdr_projects/glyphs.tsv` (`<glyph>\t<nerd-font name>`), preceded by the
distinct icons already in the registry. Fuzzy match on name. Returns the glyph.

### Glyph data

`scripts/gen-glyphs.py <glyphnames.json>` → `glyphs.tsv`, sorted by name, skipping the
`METADATA` entry. The TSV is committed and records the nerd-fonts version in its first
line as `# nerd-fonts <version>`.

## Stacks and phases

One stack. Rejected split: glyph data (A5) as an independent stack B — it would be
independent to land, but A7 needs it, which makes B a dependency rather than a peer, and
it's small enough that parallelism buys nothing.

### Stack A — herdr-projects v1

- **Base:** `main`
- **Owns:** `**`
- **Independent of:** —
- **Depends on:** —

| Phase | Lands | Depends on |
|---|---|---|
| A1 | Scaffold: manifest, shim, CLI skeleton, CI, size-gate config, event logger | — |
| A2 | `registry.py`: parse, validate, label, save | A1 |
| A3 | `resolve.py` + `herdr.py` + fake-herdr test harness | A2 |
| A4 | CLI `list`/`open`/`rename`/`add` + event hook | A3 |
| A5 | Glyph generator + committed `glyphs.tsv` | A1 |
| A6 | Picker main list + `popup` action | A4 |
| A7 | Add/edit flow, group picker, icon picker | A5, A6 |
| A8 | README, example config, 0.1.0 | A7 |

Copyable checklist:

- [ ] A1 — Scaffold
- [ ] A2 — Registry
- [ ] A3 — Resolution and herdr wrapper
- [ ] A4 — CLI commands and event hook
- [ ] A5 — Glyph data
- [ ] A6 — Picker main list
- [ ] A7 — Add/edit and icon picker
- [ ] A8 — Docs and 0.1.0

**A1 — Scaffold**
- `herdr-plugin.toml`: id `herdr-projects`, `min_herdr_version = "0.9.1"`, platforms
  macOS + Linux, pane `picker` (popup), actions `open` (→ `popup`), `rename`, `add`
  (→ `popup --add`), event `workspace.created` (→ `event`). All wired to stubs.
- `bin/herdr-projects` from launchpad's shim (S11); `lib/herdr_projects/__main__.py`
  inserts `lib/`; `cli.py` argparse dispatch for the whole CLI surface, each subcommand
  exits 2 `not implemented` except `--version`, `--help`, and `event`.
- `event` stub appends `HERDR_PLUGIN_EVENT` + `HERDR_PLUGIN_EVENT_JSON` to
  `hook.log` — so S10 can be checked by hand (`herdr plugin link .`, create a workspace
  from the UI and via CLI, read the log) before A4 is written. Record the answer in
  Settled as S10's resolution.
- `pyproject.toml` (dev: pytest, ruff; launchpad's ruff config), `.github/workflows/ci.yml`
  (lint + ShellCheck, tests on macos-15/ubuntu × 3.11/3.14, manifest parse) modelled on
  launchpad's.
- `.agents/plugins/stacked-planning/config.toml` from the stacked-planning example, plus
  a global exclude for `lib/herdr_projects/glyphs.tsv`.
- `tests/test_manifest.py`: manifest parses; declared panes/actions/events match the list
  above; each command points at `bin/herdr-projects`.
*Shippable when:* CI green; `sh bin/herdr-projects --version` prints `herdr-projects 0.0.0`.
After merge, re-run `gh-harden herdr-projects <CI job names>` to require the checks.
*Split seam:* CI workflow + size-gate config as their own PR ahead of the code scaffold.

**A2 — Registry**
`registry.py` with `Group`, `Project`, `Registry` dataclasses, `load(path)`,
`parse(dict)`, `validate`, `label(project)`, `bare_label`, `serialize`, `save(path)`.
Implements Registry contract (all subsections); S4, S12.
*Shippable when:* tests cover every validation error, grouped/ungrouped/override labels,
round-trip, `~` collapse, and that saving through a symlink leaves the symlink intact.
*Split seam:* `serialize`/`save` into a second PR after load/validate/label.

**A3 — Resolution and herdr wrapper**
`resolve.py` (Location → project, linked-worktree detection) and `herdr.py` (typed
functions over S9 commands: `workspaces()`, `workspace(id)`, `pane(id)`, `focus`,
`create`, `rename`, `notify`, `open_popup`, `context()`, `event()`); only `herdr.py`
spawns `herdr`. `tests/fake_herdr/` — an executable on `PATH` in tests that returns canned
JSON from a fixture dir and appends its argv to a log. Implements Resolution contract.
*Shippable when:* resolve tests pass for longest-prefix, subfolder, symlinked path, no
match, and linked worktree (real temp git repo + `git worktree add`); wrapper tests pass
against the fake.
*Split seam:* `herdr.py` + fake harness as one PR, `resolve.py` as the next.

**A4 — CLI commands and event hook**
Fill in `list`, `open`, `rename`, `add`, `event` per Commands (all subsections), plus
toasts and exit codes. Resolve S10 per A1's finding (add the `workspace.focused`
subscription and test only if needed). The `rename` action becomes usable from a
keybinding here.
*Shippable when:* CLI tests against fake herdr cover each command's success and failure
paths, the "already open" focus path, and that `event`
exits 0 on errors (amended: no `seen.json`, see Event hook). By hand: bound `rename` action relabels a real workspace.
*Split seam:* `event` (+ `seen.json`) after the four interactive commands.

**A5 — Glyph data**
`scripts/gen-glyphs.py` and generated `lib/herdr_projects/glyphs.tsv` (Glyph data).
Exempt from the size gate via A1's config.
*Shippable when:* test runs the generator on a small fixture JSON and checks format,
sorting, and METADATA skip; committed TSV's first line names the nerd-fonts version.
*Split seam:* none needed.

**A6 — Picker main list**
`picker.py` main list and the `popup` action (Picker contract: Main list): row building
and status as pure functions, fzf invocation with `--expect` keys, `enter`, `ctrl-r`,
`ctrl-d`, `ctrl-o`, invalid-registry row, missing-fzf message, popup retry on
"popup already open". `ctrl-a`/`ctrl-e` show "coming in A7" until then.
*Shippable when:* tests for row building (sorting, all four statuses, column alignment
with wide glyphs) and key→effect dispatch pass; by hand, the popup opens from a
keybinding, opens/focuses a project, and deletes one.
*Split seam:* delete + `ctrl-o` after open/rename.

**A7 — Add/edit and icon picker**
Add/edit flow, group picker (incl. new group), Icon picker (Picker contract: Add / edit
flow, Icon picker); the `add` action lands in the add flow.
*Shippable when:* flow-decision tests (add on registered path → edit, `use group icon`
offered only with a group icon, esc discards) and icon-list ordering tests pass; by hand,
add a project with a new group and a searched icon, and see it in `projects.toml`.
*Split seam:* icon picker as its own PR before the add/edit flow.

**A8 — Docs and 0.1.0**
README (install, `projects.toml` reference, suggested keybindings, screenshot),
`examples/projects.toml` validated in CI, CHANGELOG, version `0.1.0`, tag `v0.1.0`.
*Shippable when:* example config passes `registry.load` in CI; Done-when list walked by
hand and ticked.
*Split seam:* none needed.

## Forest from the trees

### Challenge

The advisor tool is unavailable in this session, so this is argued against myself.

**Strongest case against the sequence:** the Goal is a popup UX, but A1–A5 ship no popup.
Four PRs of plumbing risk shaping `registry`/`resolve`/`herdr` around a CLI nobody uses,
and the one real unknown — whether UI-created workspaces emit `workspace.created` (S10)
— sat inside A4, so a wrong assumption would surface after three PRs built on it.

**What changed:**
- A1's `event` stub now logs raw event payloads, so S10 is answered by hand at the first
  merge, before any hook logic is written.
- A4 makes the headless `rename` action work from a keybinding, so half the Goal (reset
  labels) is usable before the picker exists.

**What didn't change, and why:** picker-first was considered and rejected. Every picker
key calls the same operations as the CLI (`open`, `rename`, `add`), so building them
first under tests is the cheapest way to get a picker that is only fzf glue. A5 stays
separate from A7 because the TSV is generated data that the size gate exempts only as its
own diff.

### Drift test

1. If every phase after this one were cancelled, which Done-when box could a user tick
   today — or which later phase would now need less code because of this one? A PR with
   neither answer is scaffolding for its own sake.
2. Does this PR add anything the Settled entries or the Not doing list excluded —
   worktree handling, remote matching, discovery, color, continuous sync?

## Not doing

- **Worktree labels or suffixes** — out of scope; herdr-wkt owns worktrees (S3).
- **Layouts** — out of scope; herdr-plugin-workspace-manager.
- **Git-remote matching** — rejected (S2).
- **Auto-discovery / import** — rejected (S1).
- **Color** — rejected (S5).
- **Preserving comments in `projects.toml`** — rejected; stdlib-only writer (S12).
- **Default keybindings in the manifest** — rejected; users bind actions in their own
  `config.toml`, as with launchpad.
- **Fixing moved projects by remote** — rejected; missing-path status plus `ctrl-e` covers it.

## Log

- 2026-09-26 — phase A1 landed as #2; S10 resolved (UI-created workspaces emit `workspace.created`)
- 2026-09-26 — phase A2 landed as #3
- 2026-09-26 — phase A3 landed as #4
- 2026-09-26 — phase A4 landed as #5; `seen.json` dropped (herdr reuses workspace ids)
- 2026-09-26 — phase A5 landed as #6 (nerd-fonts 3.5.1)
- 2026-09-26 — phase A6 landed as #7
- 2026-09-26 — phase A7 landed as #8
