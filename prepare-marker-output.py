#!/usr/bin/env python3
"""Prepare one Marker 2.0 ISA conversion for this repository."""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
from pathlib import Path

from PIL import Image


NOTICE = (
    "> **Repository notice (not part of the AMD publication).** This is an "
    "unofficial Markdown conversion of the [AMD source PDF]({source_url}), "
    "produced with automated tooling for easier browsing and text search. It "
    "is not affiliated with or endorsed by AMD and may contain errors and "
    "omissions. AMD retains its rights in the underlying publication; AMD's "
    "own agreement, disclaimer, and copyright and trademark notices are "
    "reproduced below. Consult the linked PDF as the authoritative version."
)

IMAGE_REF = re.compile(r"^!\[\]\(([^)]+\.jpeg)\)\s*$")
PAGE_ID = re.compile(r"^_page_(\d+)_")


def image_order(path: Path) -> tuple[int, str]:
    if "_Figure_" in path.name:
        return (0, path.name)
    if "_Diagram_" in path.name:
        return (1, path.name)
    return (2, path.name)


def retained_images(generated_dir: Path) -> tuple[dict[str, Path], set[str]]:
    retained: dict[str, Path] = {}
    skipped: set[str] = set()
    seen_on_page: set[tuple[str, str]] = set()

    for path in sorted(generated_dir.glob("*.jpeg"), key=image_order):
        with Image.open(path) as image:
            width, _height = image.size

        # Marker labels logos, note icons, warning icons, and printed red
        # cross-reference numbers as Picture blocks. Technical Picture blocks
        # in these manuals are full-width encoding diagrams.
        if "_Picture_" in path.name and width < 500:
            skipped.add(path.name)
            continue

        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        page_match = PAGE_ID.match(path.name)
        page = page_match.group(1) if page_match else ""
        duplicate_key = (page, digest)
        if duplicate_key in seen_on_page:
            skipped.add(path.name)
            continue
        seen_on_page.add(duplicate_key)
        retained[path.name] = path

    return retained, skipped


def prepare(args: argparse.Namespace) -> None:
    generated_dir = args.generated_dir.resolve()
    manual_dir = args.manual_dir.resolve()
    source_markdown = generated_dir / f"{args.slug}.md"
    source_metadata = generated_dir / f"{args.slug}_meta.json"
    if not source_markdown.is_file() or not source_metadata.is_file():
        raise SystemExit(f"Marker output is incomplete: {generated_dir}")

    retained, skipped = retained_images(generated_dir)
    output_lines: list[str] = []
    for line in source_markdown.read_text(encoding="utf-8").splitlines():
        match = IMAGE_REF.match(line)
        if match:
            name = Path(match.group(1)).name
            if name in skipped:
                continue
            if name not in retained:
                raise SystemExit(f"Unclassified image reference: {name}")
            line = f"![](assets/{name})"
        output_lines.append(line)

    body = "\n".join(output_lines).strip()
    body = re.sub(r"\n{3,}", "\n\n", body)
    markdown = NOTICE.format(source_url=args.source_url) + "\n\n" + body + "\n"

    manual_dir.mkdir(parents=True, exist_ok=True)
    (manual_dir / "README.md").write_text(markdown, encoding="utf-8")
    shutil.copy2(source_metadata, manual_dir / args.metadata_name)

    assets_dir = manual_dir / "assets"
    if assets_dir.exists():
        shutil.rmtree(assets_dir)
    assets_dir.mkdir()
    for name, source in sorted(retained.items()):
        shutil.copy2(source, assets_dir / name)

    print(
        f"Prepared {args.slug}: {len(retained)} technical images retained, "
        f"{len(skipped)} decorative or duplicate images removed"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("generated_dir", type=Path)
    parser.add_argument("manual_dir", type=Path)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--metadata-name", required=True)
    parser.add_argument("--source-url", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    prepare(parse_args())
