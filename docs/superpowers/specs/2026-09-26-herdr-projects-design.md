# herdr-projects — design

Date: 2026-09-26
Status: draft, awaiting review

## Purpose

A herdr plugin that keeps a curated registry of projects — name, group, nerdfont
icon, location — and uses it to:

1. **Open** a project as a herdr workspace with the right cwd and label, or focus
   it if it's already open.
2. **Relabel** a workspace from its location, so its label matches the registry.

Today labels like ` swb/edge` are typed by hand. This makes them derived.

## Scope

In scope: registry, fzf picker popup, open, rename, add/edit/delete, nerdfont
icon picker, auto-label on workspace creation.

Out of scope:

- **Worktrees.** Owned by [herdr-wkt](https://github.com/wmxscott/herdr-wkt).
  Linked worktrees are never matched or renamed.
- **Layouts.** Owned by herdr-plugin-workspace-manager.
- **Git-remote matching.** Open needs a path anyway; some projects have no remote;
  remotes collide with worktrees and monorepo subfolders.
- **Auto-discovery.** The registry is curated.
- **Color.** herdr labels are plain text; sidebar token styles are fixed in
  `config.toml`, so per-workspace color would need a per-color token workaround.

## Registry

File: `$(herdr plugin config-dir herdr-projects)/projects.toml`. May be a
symlink (e.g. stowed from dotfiles).

```toml
[[groups]]
name = "swb"          # required, unique; label prefix
icon = ""            # optional; default icon for its projects

[[projects]]
name = "edge"         # required
group = "swb"         # optional; must reference a group name
icon = ""            # optional if its group has an icon
path = "~/Developer/switchbit-dev/edge"   # required
```

Validation:

- Group names unique. Project labels unique (ignoring icon). Project paths unique
  after resolution.
- A project's `group` must exist.
- Every project must end up with an icon (its own, or its group's).
- Unknown keys are errors.

A missing path is **not** a validation error; it's shown as `󰌸` in the picker.

### Label

```
<icon> <group.name>/<name>    # grouped
<icon> <name>                 # ungrouped
```

Project `icon` overrides group `icon`.

### Writing

stdlib `tomllib` reads only, so the plugin has a small serializer for this flat
schema. Picker edits rewrite the whole file: groups first, then projects, sorted
by group then name. Hand-written comments are not preserved.

Writes are atomic — temp file next to the target, then rename — and go to the
file's `realpath`, so a stow symlink stays a symlink.

## Resolving a location to a project

Input: an absolute path (the "location").

1. If the location is inside a **linked** git worktree → no match. Detected from
   herdr's workspace `worktree.is_linked_worktree` when available, otherwise
   `git rev-parse --git-dir` ≠ `--git-common-dir`.
2. `realpath` the location and every project path. The project with the
   **longest** path that equals or contains the location wins.
3. Otherwise → no match.

Subfolders of a project get the project's label, unchanged.

Location source:

- Manual rename: the focused pane's `cwd` (`herdr pane current`).
- Hook: the new workspace's first pane `cwd`.

## "Already open"

A workspace is the open instance of project P when it's not a linked worktree
and its location (active pane cwd) resolves to P. Matching on location, not
label, means manual relabels still count as open. If several match, the first in
herdr's workspace order wins.

## Picker (popup pane)

fzf in a herdr popup, same approach as herdr-launchpad.

```
  swb/edge          ~/Developer/switchbit-dev/edge      
  swb/kb            ~/Developer/switchbit-dev/kb
  quiesce/app       ~/Developer/onethingapp/app         
  dotfiles          ~/.config/dotfiles                  
  old-thing         ~/Developer/old-thing               󰌸
```

Sorted by group, then name. Status column:

| Glyph | Codepoint | Meaning |
|---|---|---|
| `` | U+F444 | open, and the currently focused workspace |
| `` | U+F4C3 | open |
| `󰌸` | U+F0338 | path missing |

| Key      | Action |
|----------|--------|
| `enter`  | Open: focus existing workspace, else `herdr workspace create --cwd <path> --label <label> --focus` |
| `ctrl-r` | Rename the current workspace from its location |
| `ctrl-a` | Add the current pane's cwd |
| `ctrl-e` | Edit the selected project |
| `ctrl-d` | Delete the selected project (y/n prompt) |
| `ctrl-o` | Open `projects.toml` in `$EDITOR` |

### Add / edit flow

Chained prompts in the popup:

1. **Name** — default: basename of the path (add) or current name (edit).
2. **Group** — fzf over existing groups + `none` + `+ new group`. New group
   prompts for name and icon (icon via the icon picker, skippable).
3. **Icon** — icon picker. Offers `use group icon` first when the group has one.

Adding a path that's already registered switches to editing that project.
Cancelling (esc) at any step discards the whole flow.

### Icon picker

fzf over bundled `lib/herdr_projects/glyphs.tsv` (`<glyph>\t<name>` rows).
Icons already used in the registry are listed first.

`scripts/gen-glyphs.py` generates the TSV from nerd-fonts' `glyphnames.json`.
The TSV is committed; nothing is fetched at runtime.

## Plugin surface

`herdr-plugin.toml`:

- **Pane** `picker` — popup, runs `bin/herdr-projects picker`.
- **Actions**
  - `open` — show the picker popup.
  - `rename` — rename the current workspace in place; result as a toast.
  - `add` — show the popup straight into the add flow for the current pane's cwd.
- **Event** `workspace.created` → `bin/herdr-projects event`.

No default keybindings; the user binds actions in `config.toml`.

### Auto-label hook

On `workspace.created`, read the workspace id from `HERDR_PLUGIN_EVENT_JSON`,
resolve its location, and rename it if a project matches and the label differs.

It runs once per workspace, so later manual renames are never overwritten.

**Open risk:** herdr-plugin-workspace-manager notes that UI-created workspaces
may not emit `workspace.created`. Verify this first. If it's true, also listen
to `workspace.focused` and keep a set of seen workspace ids in
`$HERDR_PLUGIN_STATE_DIR/seen.json`. Only the first sighting of an id is
handled, and its early exit must stay cheap.

## CLI

Same entry point as the plugin, usable from a shell:

```
herdr-projects list                 # label<TAB>path<TAB>status
herdr-projects open <group/name|name>   # bare name must be unambiguous
herdr-projects rename [--workspace <id>]
herdr-projects add [path] [--name N] [--group G] [--icon I]
herdr-projects picker [--add]       # used by the popup pane
herdr-projects event                # used by the event hook
```

## Architecture

Python ≥ 3.11 stdlib plus `fzf`. No other runtime dependencies.

```
herdr-plugin.toml
bin/herdr-projects          sh shim: finds and caches a Python ≥ 3.11 (from launchpad)
lib/herdr_projects/
  __main__.py               entry; puts lib/ on sys.path (the shim runs python -I)
  registry.py               load, validate, save; Group, Project, label()
  resolve.py                location → project; linked-worktree detection
  herdr.py                  wrapper over `herdr workspace|pane|notification` JSON
  picker.py                 fzf flows: main list, add/edit, group, icon
  cli.py                    argv dispatch
  glyphs.tsv                generated
scripts/gen-glyphs.py
tests/
```

Units and their dependencies:

- `registry` — pure; files only.
- `resolve` — depends on `registry` types and `git`; no herdr.
- `herdr` — the only module that shells out to `herdr`.
- `picker` — depends on `registry`, `resolve`, `herdr`; the only module that
  runs `fzf`. Row formatting and flow decisions are pure functions.
- `cli` — wires the others together.

## Errors

| Situation | Behavior |
|-----------|----------|
| Invalid TOML or validation error | Picker shows the error as its only row; `ctrl-o` opens the file |
| Hook failure | Silent; append to `$HERDR_PLUGIN_STATE_DIR/hook.log`; exit 0 |
| Manual rename, no match | Toast: `No project for <location>` |
| Manual rename, success | Toast: `Renamed to <label>` |
| Open with missing path | Toast with the path; row keeps `󰌸` |
| herdr call fails | Toast with herdr's error message |
| `fzf` not on PATH | Popup prints the requirement and waits for enter |

## Testing

pytest + ruff, as in herdr-launchpad.

- **registry**: parse and validation errors; serialize → parse round-trip; label
  building (grouped, ungrouped, icon override).
- **resolve**: longest-prefix, subfolders, symlinked paths, no match, linked
  worktrees skipped (temp git repos).
- **cli**: `list`, `open`, `rename`, `add`, `event` against a fake `herdr` on
  `PATH` that records calls and returns canned JSON.
- **manifest**: panes, actions, and events declared as specified.
- **picker**: row formatting and flow decisions as pure functions; the fzf
  interaction itself is checked by hand.
