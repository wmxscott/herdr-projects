# herdr-projects

[![CI](https://github.com/wmxscott/herdr-projects/actions/workflows/ci.yml/badge.svg)](https://github.com/wmxscott/herdr-projects/actions/workflows/ci.yml)

A [Herdr](https://herdr.dev) plugin that keeps a list of your projects and opens each one as a workspace, labelled with its icon, group and name, like ` work/api`.

You list the projects in a config file, or add them from a popup. One key opens the picker: choose a project and Herdr focuses its workspace, or creates one in the project's directory with the right label. New workspaces in a project's directory get its label on their own, and one more key resets a workspace's label after you've changed it.

<!-- screenshot: picker popup -->

```
>

 ↵  open    ^a  add    ^e  edit 
^r rename · ^d delete · ^o edit file · esc close

     oss                                               1 / 1
  └   ripgrep  ~/src/oss/ripgrep                            
     sandbox                                           0 / 0
     work                                              1 / 3
  │   api      ~/src/work/api                               
  │   docs     ~/src/work/docs                              󰌸
  └   web      ~/src/work/web
    dotfiles   ~/.dotfiles
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

A linked git worktree never belongs to a project, even inside one: it isn't labelled, and `enter` opens the project's own workspace, not a worktree's. [herdr-wkt](https://github.com/wmxscott/herdr-wkt) owns worktrees and their labels.

A workspace's directory is the working directory of the focused pane in its active tab. So a project counts as open when some workspace sits in it, whatever that workspace is called. A workspace Herdr reports as a linked worktree counts too, for the project whose path is or contains its repository's main checkout (or, for a `.bare` layout, the directory holding the bare repository): it makes that project open, and active while it's focused. A workspace Herdr reports no worktree for, like a `.bare` layout's container, goes by its directory alone, even when its pane is inside one of the container's worktrees.

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

Groups come first, sorted by name, each on a header row: its icon (a folder when it has none) and name, then `open / total`, how many of its projects are open out of how many it has. Its projects follow on a spine, sorted by name, each showing its icon, name, path and status. Projects without a group come last, with their whole label. Rows fill the popup's width; in a narrow one, paths lose their start first.

`enter` on a group's header folds the group, hiding its projects; `enter` again unfolds it. Folds last until the picker closes.

Type to search. The search matches projects' labels, `group/name`, and nothing else: not group headers, paths, counts or icons. While you type, the picker lists the matching projects by their whole label, folded groups' too, and goes back to groups when the query is empty. `wo` finds:

```
    work/api     ~/src/work/api                             
    work/web     ~/src/work/web
    work/docs    ~/src/work/docs                            󰌸
```

| Status | |
|---|---|
| `` | Open, in the workspace you're in (its own or a worktree's) |
| `` | Open in another workspace (its own or a worktree's) |
| `󰌸` | The path doesn't exist, so `enter` can't open it |

| Key | |
|---|---|
| `enter` | Open the project: focus its workspace, or create one in its directory, with its label, and focus that. On a group's header, fold or unfold it |
| `ctrl-r` | Label the current workspace after its project, like the `rename` action, and close |
| `ctrl-a` | Add the focused pane's directory. If it's already a project, edit that project instead |
| `ctrl-e` | Edit the selected project, or group |
| `ctrl-d` | Delete the selected project, or empty group, after a `y`. A group with projects says to move or delete them first |
| `ctrl-o` | Open `projects.toml` in `$EDITOR` (default `vi`), then reload |
| `esc` | Close |

Adding and editing ask, in turn, for:

1. **Name.** Defaults to the directory's name, or the current name.
2. **Group.** One of yours, `none`, or `+ new group`, which asks for the group's name and then, optionally, its icon.
3. **Icon.** `use group icon` comes first when the group has one, then the icons you already use, then every Nerd Font glyph, searched by name.

Editing a group asks for its name, then its icon: `keep current` when it has one, `no icon`, then the icons you already use, then every glyph. Renaming a group moves its projects along with it.

`esc` at any step throws the whole change away. A change that breaks one of the [rules](#rules), like a group name that's taken or a group icon a project still needs, isn't saved, and the picker says why. A linked worktree can't be added.

### Theme

The picker is drawn in [Catppuccin](https://catppuccin.com) Latte when the system is light and Macchiato when it's dark, checked each time the picker opens:

1. `HERDR_PROJECTS_THEME` in Herdr's environment, when it's `light` or `dark`. `auto`, the default, goes on to the next steps.
2. The appearance in `${XDG_DATA_HOME:-~/.local/share}/theme-monitor/theme-change.trigger`, the file theme-monitor keeps, when it says `light` or `dark`.
3. On macOS, the system's appearance setting.
4. Otherwise, light.

The theme colours the rows and headers, the add and edit steps' too. fzf's own prompt, pointer and match highlights keep fzf's colours, since the picker passes no `--color`. To change them, set `--color` in `FZF_DEFAULT_OPTS`, like `--color=light` for a light terminal.

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
