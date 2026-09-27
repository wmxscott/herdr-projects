# herdr-projects

[![CI](https://github.com/wmxscott/herdr-projects/actions/workflows/ci.yml/badge.svg)](https://github.com/wmxscott/herdr-projects/actions/workflows/ci.yml)

A [Herdr](https://herdr.dev) plugin that keeps a list of your projects and opens each one as a workspace, labelled with its icon, group and name, like ` work/api`.

You list the projects in a config file, or add them from a popup. One key opens the picker: choose a project and Herdr focuses its workspace, or creates one in the project's directory with the right label. New workspaces in a project's directory get its label on their own, and one more key resets a workspace's label after you've changed it.

<!-- screenshot: picker popup -->

```
>
  enter open · ^r rename · ^a add · ^e edit · ^d delete · ^o edit file
    dotfiles     ~/.dotfiles
    oss/ripgrep  ~/src/oss/ripgrep  
    work/api     ~/src/work/api     
    work/docs    ~/src/work/docs    󰌸
    work/web     ~/src/work/web
```

## Requirements

- Herdr 0.9.1 or newer, on macOS or Linux
- Python 3.11 or newer on `PATH`. macOS's own `/usr/bin/python3` is too old; Homebrew's `python` is fine. The plugin looks for one the first time it runs and remembers its path in the file `python` in Herdr's state directory for the plugin, usually `~/.local/state/herdr/plugins/herdr-projects/`. Delete that file to make it look again
- [fzf](https://github.com/junegunn/fzf), for the picker
- A [Nerd Font](https://www.nerdfonts.com) in your terminal, for the icons. The icon picker lists Nerd Font glyphs, but any character or emoji works as an icon

## Install

```sh
herdr plugin install wmxscott/herdr-projects
```

Herdr shows what the plugin will run and asks before installing; `--yes` skips that. Pin a version with `--ref <tag>`. There is no `herdr plugin update`: run the install again to update.

Then bind keys to its actions in Herdr's `config.toml` (see [Keybindings](#keybindings)), and add projects from the picker with `ctrl-a`, or start from the example:

```sh
curl -fsSL --create-dirs https://raw.githubusercontent.com/wmxscott/herdr-projects/main/examples/projects.toml \
  -o "$(herdr plugin config-dir herdr-projects)/projects.toml"
```

## `projects.toml`

The project list lives in the plugin's config directory, which `herdr plugin config-dir herdr-projects` prints. That's usually `~/.config/herdr/plugins/config/herdr-projects/projects.toml`. A missing file is an empty list. The picker reads it each time it opens, so hand edits apply straight away.

```toml
[[groups]]
name = "work"
icon = "\uf0b1"          # fa-briefcase

[[projects]]
name = "api"
group = "work"
path = "~/src/work/api"   # labelled " work/api"

[[projects]]
name = "docs"
group = "work"
icon = "\uf405"          # oct-book, instead of the group's
path = "~/src/work/docs"

[[projects]]
name = "dotfiles"
icon = "\ue5fc"          # custom-folder_config
path = "~/.dotfiles"      # labelled " dotfiles"
```

[`examples/projects.toml`](examples/projects.toml) is a longer version.

### `[[groups]]`

| Key | | |
|---|---|---|
| `name` | *(required)* | The label's prefix. Unique |
| `icon` | *(none)* | Icon for the group's projects that have none of their own |

### `[[projects]]`

| Key | | |
|---|---|---|
| `name` | *(required)* | The rest of the label |
| `group` | *(none)* | The `name` of a group |
| `icon` | the group's | Required when the project has no group, or its group has no icon |
| `path` | *(required)* | The project's directory: absolute, or starting with `~`. It needn't exist; the picker marks a missing one |

### Labels

```
<icon> <group>/<name>    # in a group
<icon> <name>            # without one
```

A project's own `icon` wins over its group's.

### Rules

- Every value is a string that isn't blank. Unknown keys are errors.
- Group names are unique, and a project's `group` must name one.
- Every project ends up with an icon, its own or its group's.
- Labels are unique, not counting the icon, so `work/api` and `oss/api` can both exist.
- A `path` is absolute or starts with `~`.
- Paths are unique once `~` and symlinks are resolved.

When the file breaks a rule, or isn't valid TOML, the picker shows the first problem as its only row, and `ctrl-o` opens the file to fix it. `herdr-projects list` prints every problem, each with where it is, like `projects[2]`.

### Saving

Adding, editing and deleting from the picker rewrite the whole file: groups, then projects sorted by group and name, with paths under your home directory written with `~`. **Comments aren't kept.** The file may be a symlink, for example into a dotfiles repository: saves write to the file it points at, so it stays a symlink.

## Which project a directory belongs to

A directory belongs to the project whose `path` is that directory or contains it, the deepest one when several do. Symlinks are resolved first. Subfolders get their project's label unchanged.

A linked git worktree never belongs to a project, even inside one. [herdr-wkt](https://github.com/wmxscott/herdr-wkt) owns worktrees and their labels.

A workspace's directory is the working directory of the focused pane in its active tab. So a project counts as open when some workspace sits in it, whatever that workspace is called.

## Keybindings

The plugin has three actions, and no keys of its own. Bind them in Herdr's `config.toml`:

| Action | Does |
|---|---|
| `herdr-projects.open` | Opens the picker |
| `herdr-projects.rename` | Labels the current workspace after the project its focused pane is in, and says what it did in a toast |
| `herdr-projects.add` | Opens the picker in the add flow, for the focused pane's directory |

For example:

```toml
[[keys.command]]
key = "prefix+f"
type = "plugin_action"
command = "herdr-projects.open"
description = "projects"

[[keys.command]]
key = "prefix+shift+l"
type = "plugin_action"
command = "herdr-projects.rename"
description = "label workspace after its project"

[[keys.command]]
key = "prefix+shift+a"
type = "plugin_action"
command = "herdr-projects.add"
description = "add project"
```

Run `herdr server reload-config`, or restart Herdr, to pick up new keys. `herdr plugin action list --plugin herdr-projects` lists the actions.

## The picker

Each row is a project's icon, label, path and status, sorted by group and then name. Type to filter.

| Status | |
|---|---|
| `` | Open, in the workspace you're in |
| `` | Open in another workspace |
| `󰌸` | The path doesn't exist, so `enter` can't open it |

| Key | |
|---|---|
| `enter` | Open the project: focus its workspace, or create one in its directory, with its label, and focus that |
| `ctrl-r` | Label the current workspace after its project, like the `rename` action, and close |
| `ctrl-a` | Add the focused pane's directory. If it's already a project, edit that project instead |
| `ctrl-e` | Edit the selected project |
| `ctrl-d` | Delete the selected project, after a `y` |
| `ctrl-o` | Open `projects.toml` in `$EDITOR` (default `vi`), then reload |
| `esc` | Close |

Adding and editing ask, in turn, for:

1. **Name.** Defaults to the directory's name, or the current name.
2. **Group.** One of yours, `none`, or `+ new group`, which asks for the group's name and then, optionally, its icon.
3. **Icon.** `use group icon` comes first when the group has one, then the icons you already use, then every Nerd Font glyph, searched by name.

`esc` at any step throws the whole change away. A linked worktree can't be added.

## Labelling new workspaces

When Herdr creates a workspace, from its own UI or with `herdr workspace create`, this plugin labels it after the project its directory belongs to. That happens once, when the workspace is created, so a label you change by hand later stays. Linked worktrees are left alone.

Workspaces Herdr restores or creates at startup don't count as new. Use the `rename` action on those.

Problems in this hook never show up in Herdr. They go to `hook.log` in the plugin's state directory, usually `~/.local/state/herdr/plugins/herdr-projects/`.

## Command line

`bin/herdr-projects` in the plugin's directory is also a command. `herdr plugin list --plugin herdr-projects --json` prints that directory as `plugin_root`. Run it with `sh`, or alias it:

```
herdr-projects list                        # group/name, path and status (active, open, missing or -), tab-separated
herdr-projects open <group/name | name>    # a bare name must be unambiguous
herdr-projects rename [--workspace ID]     # default: the current workspace
herdr-projects add [PATH] [--name N] [--group G] [--icon I]
```

`add` defaults to the current pane's directory and that directory's name, and needs an icon from `--icon` or from a `--group` that already exists. New groups are made in the picker. The commands exit 1 with a message on stderr when something fails, and 2 on a usage error.

## Uninstall

```sh
herdr plugin uninstall herdr-projects
```

Then remove the `herdr-projects.*` bindings from Herdr's `config.toml`. Your `projects.toml` stays in `$(herdr plugin config-dir herdr-projects)` until you delete it.

## Development

```sh
uv run pytest
uv run ruff check
uv run ruff format --check
```

To try a checkout in Herdr, uninstall any installed copy, then `herdr plugin link .` from the checkout. `herdr plugin unlink herdr-projects` removes it again.

The tests run against a fake `herdr` on `PATH` that records its arguments and answers with canned JSON, so they never reach a running Herdr. The fzf prompts themselves are checked by hand.

`bin/herdr-projects` is a small `sh` script that finds Python 3.11 or newer and runs `lib/herdr_projects`, which has no dependencies beyond the standard library. The `open` and `add` actions read the list and ask Herdr which projects are open before they open the popup, so the popup only has to start fzf.

### Glyphs

The icon picker's list, `lib/herdr_projects/glyphs.tsv`, is generated from Nerd Fonts' `glyphnames.json` and committed; nothing is fetched at runtime. Its first line names the Nerd Fonts version. To regenerate it for another release:

```sh
tag=v3.5.1
curl -fsSLO "https://raw.githubusercontent.com/ryanoasis/nerd-fonts/$tag/glyphnames.json"
python3 scripts/gen-glyphs.py glyphnames.json
```

## License

[MIT](LICENSE)
