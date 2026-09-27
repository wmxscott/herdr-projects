# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-09-26

### Added

- A project list in `projects.toml`, in the plugin's config directory: groups and projects, each with a Nerd Font icon, validated on load. Saves are atomic and keep a symlinked file a symlink.
- Workspace labels derived from the list: `<icon> <group>/<name>`, or `<icon> <name>` without a group.
- The picker popup (`open` action): open or focus a project's workspace, relabel the current workspace, and add, edit or delete projects, with a group picker and a searchable icon picker over the Nerd Fonts glyph list.
- The `rename` action, which labels the current workspace after its project.
- The `add` action, which opens the picker in the add flow for the focused pane's directory.
- Automatic labelling of new workspaces in a project's directory, once, on `workspace.created`. Linked git worktrees are never matched.
- A command line: `list`, `open`, `rename` and `add`.
- `scripts/gen-glyphs.py`, which generates the icon picker's glyph list from Nerd Fonts' `glyphnames.json` (committed for Nerd Fonts 3.5.1).
- An example `projects.toml`, checked in CI.

[Unreleased]: https://github.com/wmxscott/herdr-projects/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/wmxscott/herdr-projects/releases/tag/v0.1.0
