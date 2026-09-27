# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-09-27

### Added

- A project list in `projects.toml`, in the plugin's config directory: groups and projects, each with a Nerd Font icon, validated on load. Saves are atomic and keep a symlinked file a symlink.
- Workspace labels derived from the list: `<icon> <group>/<name>`, or `<icon> <name>` without a group.
- The picker popup (`open` action): open or focus a project's workspace, relabel the current workspace, and add, edit or delete projects, with a group picker and a searchable icon picker over the Nerd Fonts glyph list.
- Grouped picker rows: each group, empty ones included, on a header row with its project and open counts, its projects on a spine under it, and ungrouped projects after the groups. `enter` on a header folds it.
- Group editing from the picker: `ctrl-e` on a header renames the group, moving its projects along, and changes its icon; `ctrl-d` deletes an empty group.
- A Catppuccin theme for the picker, Latte when light and Macchiato when dark, following the system appearance or `HERDR_PROJECTS_THEME`. Rows fill the popup's width, with dim paths and coloured status icons.
- The `rename` action, which labels the current workspace after its project.
- The `add` action, which opens the picker in the add flow for the focused pane's directory.
- Automatic labelling of new workspaces in a project's directory, once, on `workspace.created`. Linked git worktrees are never matched.
- A command line: `list`, `open`, `rename` and `add`.
- `scripts/gen-glyphs.py`, which generates the icon picker's glyph list from Nerd Fonts' `glyphnames.json` (committed for Nerd Fonts 3.5.1).
- An example `projects.toml`, checked in CI.

[Unreleased]: https://github.com/wmxscott/herdr-projects/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/wmxscott/herdr-projects/releases/tag/v1.0.0
