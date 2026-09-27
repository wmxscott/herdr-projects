#!/usr/bin/env python3
"""Generate the icon picker's glyph list from nerd-fonts' glyphnames.json.

glyphnames.json sits at the root of the ryanoasis/nerd-fonts repository, per release tag:
https://raw.githubusercontent.com/ryanoasis/nerd-fonts/<tag>/glyphnames.json

The output is UTF-8: a `# nerd-fonts <version>` line, then one `<glyph>\\t<name>` row per
glyph, sorted by name.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "lib" / "herdr_projects" / "glyphs.tsv"


def render(data: object) -> str:
    metadata = data.get("METADATA") if isinstance(data, dict) else None
    version = metadata.get("version") if isinstance(metadata, dict) else None
    if not isinstance(version, str) or not version or any(c.isspace() for c in version):
        raise ValueError("no METADATA version")
    lines = [f"# nerd-fonts {version}"]
    for name in sorted(data):
        if name == "METADATA":
            continue
        if not name or not name.isprintable() or " " in name:
            raise ValueError(f"bad name {name!r}")
        entry = data[name]
        char = entry.get("char") if isinstance(entry, dict) else None
        # A `#` glyph would read as a comment line.
        if not isinstance(char, str) or len(char) != 1 or char.isspace() or char == "#":
            raise ValueError(f"{name}: bad char {char!r}")
        lines.append(f"{char}\t{name}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gen-glyphs.py", description=__doc__.splitlines()[0])
    parser.add_argument("glyphnames", type=Path, help="nerd-fonts glyphnames.json")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="output TSV (default: lib/herdr_projects/glyphs.tsv in this repository)",
    )
    args = parser.parse_args(argv)
    try:
        text = render(json.loads(args.glyphnames.read_text(encoding="utf-8")))
    except (OSError, ValueError) as error:
        print(f"gen-glyphs.py: {args.glyphnames}: {error}", file=sys.stderr)
        return 1
    args.output.write_text(text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
