#!/usr/bin/env python3
"""Import one Marker 2.0 AMD publication conversion into this repository."""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
from pathlib import Path

from PIL import Image


MANUAL_NOTICE = (
    "> **Repository notice (not part of the AMD publication).** This is an "
    "unofficial Markdown conversion of the [AMD source PDF]({source_url}), "
    "produced with automated tooling for easier browsing and text search. It "
    "is not affiliated with or endorsed by AMD and may contain errors and "
    "omissions. AMD retains its rights in the underlying publication; AMD's "
    "own agreement, disclaimer, and copyright and trademark notices are "
    "reproduced below. Consult the linked PDF as the authoritative version."
)
WHITEPAPER_NOTICE = (
    "> **Repository notice (not part of the AMD publication).** This is an "
    "unofficial Markdown conversion of the [AMD source PDF]({source_url}), "
    "produced with automated tooling for easier browsing and text search. It "
    "is not affiliated with or endorsed by AMD and may contain errors and "
    "omissions. AMD retains its rights in the underlying publication; AMD's "
    "copyright and trademark notice from the source is reproduced below. "
    "Consult the linked PDF as the authoritative version."
)

IMAGE_REF = re.compile(r"!\[\]\(([^)]+\.jpeg)\)")
PAGE_ID = re.compile(r"^_page_(\d+)_")
PAGE_HEADING = re.compile(
    r'^#{1,6}\s+<span id="([^"]+)"></span>(.+?)\s*$'
)
CONTENTS_HEADING = re.compile(
    r"^#{1,6}\s+\**(?:table of )?contents\**\s*$", re.IGNORECASE
)
TOC_ROW = re.compile(
    r"^(\|\s*)(.*?)(\s*\|\s*)(\d+(?:\s*[-–]\s*\d+)?)(\s*\|)$"
)
LINKED_LABEL = re.compile(r"^\[(.*)\]\(#[^)]+\)$")


def image_order(path: Path) -> tuple[int, str]:
    if "_Figure_" in path.name:
        return (0, path.name)
    if "_Diagram_" in path.name:
        return (1, path.name)
    return (2, path.name)


def retained_images(
    generated_dir: Path, excluded: set[str]
) -> tuple[dict[str, Path], set[str]]:
    retained: dict[str, Path] = {}
    skipped: set[str] = set()
    seen_on_page: set[tuple[str, str]] = set()
    available = {path.name for path in generated_dir.glob("*.jpeg")}
    unknown = excluded - available
    if unknown:
        raise SystemExit("Unknown excluded images: " + ", ".join(sorted(unknown)))

    for path in sorted(generated_dir.glob("*.jpeg"), key=image_order):
        if path.name in excluded:
            skipped.add(path.name)
            continue
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


def table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def append_fragment(existing: str, fragment: str, column_name: str) -> str:
    if not existing:
        return fragment
    if (
        "name" in column_name.lower()
        and "_" in existing
        and re.fullmatch(r"[A-Z][A-Z0-9_]*", existing)
        and re.fullmatch(r"[A-Z0-9_]+", fragment)
    ):
        return existing + fragment
    if existing.endswith("-") and fragment[:1].islower():
        return existing + fragment
    return f"{existing} {fragment}"


def merge_rows(previous: str, continuation: str, headers: list[str]) -> str:
    prior_cells = table_cells(previous)
    next_cells = table_cells(continuation)
    if len(prior_cells) != len(next_cells) or len(prior_cells) != len(headers):
        return previous
    merged = [
        append_fragment(prior_cells[i], next_cells[i], headers[i])
        if next_cells[i]
        else prior_cells[i]
        for i in range(len(headers))
    ]
    return "| " + " | ".join(merged) + " |"


def compact_table(block: list[str]) -> list[str]:
    if len(block) < 3:
        return block
    headers = table_cells(block[0])
    if not headers or not headers[0]:
        return block
    first_row_is_data = not headers[0][:1].isalpha()
    rows: list[str] = []
    for row in block[2:]:
        cells = table_cells(row)
        if cells and not cells[0]:
            if rows:
                rows[-1] = merge_rows(rows[-1], row, headers)
            elif first_row_is_data:
                block[0] = merge_rows(block[0], row, headers)
            else:
                rows.append(row)
        else:
            rows.append(row)
    return block[:2] + rows


def compact_table_continuations(markdown: str) -> str:
    """Join wrapped rows, including rows split across PDF page boundaries."""
    lines = markdown.splitlines()
    segments: list[tuple[str, list[str]]] = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("|") and lines[i].endswith("|"):
            block: list[str] = []
            while i < len(lines) and lines[i].startswith("|") and lines[i].endswith("|"):
                block.append(lines[i])
                i += 1
            segments.append(("table", compact_table(block)))
        else:
            text: list[str] = []
            while i < len(lines) and not (
                lines[i].startswith("|") and lines[i].endswith("|")
            ):
                text.append(lines[i])
                i += 1
            segments.append(("text", text))

    previous_table: int | None = None
    for index, (kind, block) in enumerate(segments):
        if kind == "text":
            if any(line.strip() for line in block):
                previous_table = None
            continue
        if previous_table is not None:
            prior = segments[previous_table][1]
            if (
                len(prior) >= 3
                and len(block) >= 3
                and table_cells(prior[0]) == table_cells(block[0])
            ):
                if table_cells(block[2]) and not table_cells(block[2])[0]:
                    prior[-1] = merge_rows(
                        prior[-1], block[2], table_cells(prior[0])
                    )
                    del block[2]
                prior.extend(block[2:])
                block.clear()
                continue
        previous_table = index

    return "\n".join(line for _kind, segment in segments for line in segment)


def plain_heading(text: str) -> str:
    """Remove the small amount of Markdown used in headings and TOC labels."""
    linked = LINKED_LABEL.fullmatch(text.strip())
    if linked:
        text = linked.group(1)
    text = re.sub(r"<[^>]+>", " ", text)
    return text.replace("\\", "").replace("*", "").replace("`", "").strip()


def heading_key(text: str) -> str:
    text = plain_heading(text).lower().replace("’", "'")
    text = re.sub(r"^chapter\s+", "", text)
    return " ".join(re.findall(r"[a-z0-9]+", text))


def section_number(text: str) -> str | None:
    match = re.match(
        r"^(?:chapter\s+)?(\d+(?:\.\d+)*)(?:\.|\s)",
        plain_heading(text),
        re.IGNORECASE,
    )
    return match.group(1) if match else None


def link_table_of_contents(markdown: str) -> tuple[str, int, list[str]]:
    """Link numeric-page TOC rows to explicit page anchors in the document."""
    lines = markdown.splitlines()
    headings: list[tuple[str, str]] = []
    first_page_heading: int | None = None
    for index, line in enumerate(lines):
        match = PAGE_HEADING.match(line)
        if not match:
            continue
        if first_page_heading is None:
            first_page_heading = index
        headings.append((match.group(1), plain_heading(match.group(2))))

    by_key: dict[str, list[str]] = {}
    by_section: dict[str, list[str]] = {}
    for anchor, title in headings:
        by_key.setdefault(heading_key(title), []).append(anchor)
        section = section_number(title)
        if section:
            by_section.setdefault(section, []).append(anchor)

    contents_start = next(
        (index for index, line in enumerate(lines) if CONTENTS_HEADING.match(line)),
        None,
    )
    if contents_start is None:
        return markdown, 0, []
    contents_end = first_page_heading if first_page_heading is not None else len(lines)

    linked_count = 0
    unresolved: list[str] = []
    for index in range(contents_start + 1, contents_end):
        match = TOC_ROW.match(lines[index])
        if not match:
            continue
        label = plain_heading(match.group(2))
        candidates = by_key.get(heading_key(label), [])
        if len(candidates) != 1:
            section = section_number(label)
            candidates = by_section.get(section, []) if section else candidates
        if len(candidates) != 1:
            unresolved.append(label)
            continue
        lines[index] = (
            f"{match.group(1)}[{label}](#{candidates[0]})"
            f"{match.group(3)}{match.group(4)}{match.group(5)}"
        )
        linked_count += 1

    trailing_newline = "\n" if markdown.endswith("\n") else ""
    return "\n".join(lines) + trailing_newline, linked_count, unresolved


def prepare(args: argparse.Namespace) -> None:
    generated_dir = args.generated_dir.resolve()
    manual_dir = args.manual_dir.resolve()
    source_markdown = generated_dir / f"{args.slug}.md"
    source_metadata = generated_dir / f"{args.slug}_meta.json"
    if not source_markdown.is_file() or not source_metadata.is_file():
        raise SystemExit(f"Marker output is incomplete: {generated_dir}")

    retained, skipped = retained_images(generated_dir, set(args.skip_image))
    output_lines: list[str] = []
    for line in source_markdown.read_text(encoding="utf-8").splitlines():
        for match in reversed(list(IMAGE_REF.finditer(line))):
            name = Path(match.group(1)).name
            if name in skipped:
                replacement = ""
            elif name not in retained:
                raise SystemExit(f"Unclassified image reference: {name}")
            else:
                replacement = f"![]({args.assets_name}/{name})"
            line = line[: match.start()] + replacement + line[match.end() :]
        output_lines.append(line)

    body = compact_table_continuations("\n".join(output_lines)).strip()
    body = re.sub(r"\n{3,}", "\n\n", body)
    body, linked_toc_rows, unresolved_toc_rows = link_table_of_contents(body)
    if unresolved_toc_rows:
        print(
            "Unresolved TOC entries requiring manual headings or anchors: "
            + ", ".join(unresolved_toc_rows),
            file=sys.stderr,
        )
    notice = (
        MANUAL_NOTICE if args.document_type == "manual" else WHITEPAPER_NOTICE
    )
    markdown = notice.format(source_url=args.source_url) + "\n\n" + body + "\n"

    manual_dir.mkdir(parents=True, exist_ok=True)
    (manual_dir / args.markdown_name).write_text(markdown, encoding="utf-8")
    shutil.copy2(source_metadata, manual_dir / args.metadata_name)

    assets_dir = manual_dir / args.assets_name
    if assets_dir.exists():
        shutil.rmtree(assets_dir)
    assets_dir.mkdir()
    for name, source in sorted(retained.items()):
        shutil.copy2(source, assets_dir / name)

    print(
        f"Prepared {args.slug}: {len(retained)} technical images retained, "
        f"{len(skipped)} images removed, "
        f"{linked_toc_rows} TOC entries linked"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("generated_dir", type=Path)
    parser.add_argument("manual_dir", type=Path)
    parser.add_argument("--slug", required=True)
    parser.add_argument(
        "--document-type", choices=("manual", "whitepaper"), default="manual"
    )
    parser.add_argument("--markdown-name", default="README.md")
    parser.add_argument("--metadata-name", required=True)
    parser.add_argument("--assets-name", default="assets")
    parser.add_argument("--skip-image", action="append", default=[])
    parser.add_argument("--source-url", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    prepare(parse_args())
