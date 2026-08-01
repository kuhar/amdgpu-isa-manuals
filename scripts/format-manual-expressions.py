#!/usr/bin/env python3
"""Restore PDF pseudocode layout in explicitly headed expression sections."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import textwrap
import unicodedata
from dataclasses import dataclass
from pathlib import Path


EXPRESSION_HEADING = re.compile(r"^#{1,6}\s+\*\*Expression\*\*\s*$")
ANY_HEADING = re.compile(r"^#{1,6}\s+")
PAGE_FOOTER = re.compile(r"\b\d+\s+of\s+\d+$")
DOCUMENT_HEADER = re.compile(r'^".*" Instruction Set Architecture$')
SOURCE_INSTRUCTION = re.compile(
    r"^\s*([A-Z][A-Z0-9_]+)\s+(\d+(?:\s*,\s*\d+)*)\s*$"
)
MARKDOWN_INSTRUCTION = re.compile(
    r"^#{2,6}\s+\*\*([A-Z][A-Z0-9_\\]+)\s+"
    r"(\d+(?:,\s*\d+)*)\*\*\s*$"
)
MARKDOWN_ESCAPES = frozenset(r"_*[]{}")
CONTROL_FLOW = re.compile(
    r"(?:^|\W)(?:if|then|else|endif|for|while|do|endfor|endwhile)(?:\W|$)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SourceExpression:
    instruction: tuple[str, str] | None
    text: str
    normalized: str
    match_normalized: str


@dataclass(frozen=True)
class MarkdownExpression:
    instruction: tuple[str, str] | None
    heading_index: int
    body_start: int
    body_end: int
    line_number: int


def is_page_furniture(line: str) -> bool:
    stripped = line.strip().lstrip("\f")
    return bool(
        DOCUMENT_HEADER.fullmatch(stripped) or PAGE_FOOTER.search(stripped)
    )


def normalize_with_ends(text: str) -> tuple[str, list[int]]:
    """Normalize for matching and retain each character's source end offset."""
    normalized: list[str] = []
    ends: list[int] = []
    index = 0
    while index < len(text):
        character = text[index]
        if (
            character == "\\"
            and index + 1 < len(text)
            and text[index + 1] in MARKDOWN_ESCAPES
        ):
            index += 1
            character = text[index]
        if not character.isspace() and unicodedata.category(character) != "Cc":
            normalized.append(character)
            ends.append(index + 1)
        index += 1
    return "".join(normalized), ends


def normalize(text: str) -> str:
    return normalize_with_ends(text)[0]


def pdf_text(pdf: Path) -> str:
    try:
        completed = subprocess.run(
            ["pdftotext", "-layout", str(pdf), "-"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as error:
        raise SystemExit(
            "pdftotext is required; install the Poppler command-line tools"
        ) from error
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or f"exit status {error.returncode}"
        raise SystemExit(f"pdftotext failed: {detail}") from error
    return completed.stdout


def extract_source_expressions(
    text: str, *, cross_page_boundaries: bool
) -> list[tuple[tuple[str, str] | None, str, str]]:
    lines = text.splitlines()
    expressions: list[tuple[tuple[str, str] | None, str, str]] = []
    instruction: tuple[str, str] | None = None
    index = 0
    while index < len(lines):
        instruction_match = SOURCE_INSTRUCTION.fullmatch(lines[index])
        if instruction_match:
            instruction = (
                instruction_match.group(1),
                re.sub(r"\s+", "", instruction_match.group(2)),
            )
        if lines[index].strip() != "Expression":
            index += 1
            continue

        index += 1
        while index < len(lines) and (
            not lines[index].strip() or is_page_furniture(lines[index])
        ):
            index += 1

        body: list[str] = []
        while index < len(lines):
            if lines[index].strip():
                if not is_page_furniture(lines[index]):
                    body.append(lines[index].rstrip())
                index += 1
                continue

            # Expressions occasionally cross a printed page boundary. Resume
            # only when the blank run contains page furniture and the next
            # content is still indented pseudocode. Ordinary blank lines stop
            # the block so that following notes are never absorbed.
            lookahead = index
            crossed_page = False
            while lookahead < len(lines) and (
                not lines[lookahead].strip()
                or is_page_furniture(lines[lookahead])
            ):
                crossed_page |= is_page_furniture(lines[lookahead])
                lookahead += 1
            if (
                cross_page_boundaries
                and crossed_page
                and lookahead < len(lines)
                and lines[lookahead][:1].isspace()
            ):
                index = lookahead
                continue
            break

        expression = textwrap.dedent("\n".join(body)).strip()
        normalized = normalize(expression)
        if normalized:
            expressions.append((instruction, expression, normalized))
    return expressions


def source_expressions(pdf: Path) -> list[SourceExpression]:
    text = pdf_text(pdf)
    short = extract_source_expressions(text, cross_page_boundaries=False)
    extended = extract_source_expressions(text, cross_page_boundaries=True)
    if len(short) != len(extended):
        raise SystemExit(
            "PDF expression extraction changed at page boundaries: "
            f"{len(short)} basic blocks, {len(extended)} extended blocks"
        )

    expressions: list[SourceExpression] = []
    for (
        short_instruction,
        short_text,
        short_normalized,
    ), (
        extended_instruction,
        extended_text,
        extended_normalized,
    ) in zip(short, extended, strict=True):
        if short_instruction != extended_instruction:
            raise SystemExit("PDF instruction matching changed at a page boundary")
        if extended_normalized.startswith(short_normalized):
            expressions.append(
                SourceExpression(
                    short_instruction,
                    extended_text,
                    extended_normalized,
                    short_normalized,
                )
            )
        else:
            expressions.append(
                SourceExpression(
                    short_instruction,
                    short_text,
                    short_normalized,
                    short_normalized,
                )
            )
    return expressions


def markdown_expressions(lines: list[str]) -> list[MarkdownExpression]:
    expressions: list[MarkdownExpression] = []
    instruction: tuple[str, str] | None = None
    for index, line in enumerate(lines):
        instruction_match = MARKDOWN_INSTRUCTION.fullmatch(line)
        if instruction_match:
            instruction = (
                instruction_match.group(1).replace("\\", ""),
                re.sub(r"\s+", "", instruction_match.group(2)),
            )
        if not EXPRESSION_HEADING.fullmatch(line):
            continue
        body_start = index + 1
        body_end = body_start
        while body_end < len(lines) and not ANY_HEADING.match(lines[body_end]):
            body_end += 1
        expressions.append(
            MarkdownExpression(
                instruction, index, body_start, body_end, index + 1
            )
        )
    return expressions


def formatted_parts(body: str) -> tuple[str, str] | None:
    """Return the code prefix and trailing prose from a formatted section."""
    stripped = body.lstrip()
    body_lines = stripped.splitlines()
    if not body_lines:
        return None

    fence_match = re.fullmatch(r"(`{3,})text\s*", body_lines[0])
    if fence_match:
        fence = fence_match.group(1)
        try:
            fence_end = body_lines.index(fence, 1)
        except ValueError:
            return None
        return (
            "\n".join(body_lines[1:fence_end]),
            "\n".join(body_lines[fence_end + 1 :]).strip(),
        )

    inline_match = re.fullmatch(r"`([^`]*)`", body_lines[0])
    if not inline_match:
        return None
    return inline_match.group(1), "\n".join(body_lines[1:]).strip()


def inline_expression(expression: str, maximum_length: int) -> bool:
    return bool(
        "\n" not in expression
        and len(expression) <= maximum_length
        and "`" not in expression
        and "//" not in expression
        and not CONTROL_FLOW.search(expression)
    )


def render_expression(expression: str, maximum_length: int) -> tuple[str, str]:
    if inline_expression(expression, maximum_length):
        return f"`{expression}`", "inline"
    fence = "```" if "```" not in expression else "````"
    return f"{fence}text\n{expression}\n{fence}", "block"


def keyed_source_index(
    section: MarkdownExpression,
    sources: list[SourceExpression],
    source_index: int,
) -> int | None:
    """Find the nearby PDF expression for a named Markdown instruction."""
    if section.instruction is None:
        return None
    for candidate_index in range(
        source_index, min(source_index + 4, len(sources))
    ):
        if sources[candidate_index].instruction == section.instruction:
            return candidate_index
    return None


def format_markdown(
    markdown: str,
    sources: list[SourceExpression],
    maximum_inline_length: int,
    verbose: bool,
) -> tuple[str, dict[str, int]]:
    lines = markdown.splitlines()
    sections = markdown_expressions(lines)
    source_index = 0
    replacements: list[tuple[int, int, list[str]]] = []
    counts = {
        "sections": len(sections),
        "source": len(sources),
        "inline": 0,
        "block": 0,
        "trailers": 0,
        "already": 0,
        "unmatched": 0,
        "matched_source": 0,
        "restored_prefixes": 0,
    }

    for section in sections:
        body = "\n".join(lines[section.body_start : section.body_end]).strip()
        existing = formatted_parts(body)
        if existing is not None:
            existing_expression, existing_trailer = existing
            existing_normalized = normalize(existing_expression)
            logical_body = existing_expression
            if existing_trailer:
                logical_body += "\n" + existing_trailer
            logical_normalized, logical_ends = normalize_with_ends(logical_body)
            match_index = keyed_source_index(section, sources, source_index)
            if match_index is None:
                for candidate_index in range(source_index, len(sources)):
                    candidate = sources[candidate_index]
                    if (
                        candidate.normalized == existing_normalized
                        or candidate.match_normalized == existing_normalized
                        or (
                            candidate.normalized.startswith(existing_normalized)
                            and logical_normalized.startswith(candidate.normalized)
                        )
                    ):
                        match_index = candidate_index
                        break

            if match_index is None:
                counts["already"] += 1
                continue

            counts["matched_source"] += 1
            source_index = match_index + 1
            source = sources[match_index]
            if source.normalized == existing_normalized:
                counts["already"] += 1
                continue

            if logical_normalized.startswith(source.normalized):
                prefix_end = logical_ends[len(source.normalized) - 1]
                trailer = logical_body[prefix_end:].strip()
            else:
                trailer = existing_trailer
            rendered, style = render_expression(source.text, maximum_inline_length)
            counts[style] += 1
            if trailer:
                rendered += "\n\n" + trailer
                counts["trailers"] += 1
            replacement = [""] + rendered.splitlines() + [""]
            replacements.append((section.body_start, section.body_end, replacement))
            continue

        body_normalized, body_ends = normalize_with_ends(body)
        match_index = keyed_source_index(section, sources, source_index)
        match_kind = "keyed" if match_index is not None else "prefix"
        if match_index is None:
            short_match: int | None = None
            for candidate_index in range(source_index, len(sources)):
                if body_normalized.startswith(
                    sources[candidate_index].match_normalized
                ):
                    short_match = candidate_index
                    break
            if short_match is not None:
                full_matches = [
                    candidate_index
                    for candidate_index in range(
                        source_index, min(short_match + 4, len(sources))
                    )
                    if body_normalized.startswith(
                        sources[candidate_index].normalized
                    )
                ]
                match_index = (
                    max(
                        full_matches,
                        key=lambda candidate_index: len(
                            sources[candidate_index].normalized
                        ),
                    )
                    if full_matches
                    else short_match
                )

        # Marker can lose the first line or first page of an expression while
        # retaining the remainder. Restore it only when the complete Markdown
        # body is an exact suffix of one of the next few source expressions.
        if match_index is None and body_normalized:
            for candidate_index in range(
                source_index, min(source_index + 4, len(sources))
            ):
                if sources[candidate_index].normalized.endswith(body_normalized):
                    match_index = candidate_index
                    match_kind = "suffix"
                    break

        if match_index is None:
            counts["unmatched"] += 1
            if verbose:
                preview = " ".join(body.split())[:100]
                print(
                    f"Unmatched expression at Markdown line "
                    f"{section.line_number}: {preview}",
                    file=sys.stderr,
                )
            continue

        counts["matched_source"] += 1
        source_index = match_index + 1
        source = sources[match_index]
        if match_kind == "suffix":
            trailer = ""
            counts["restored_prefixes"] += 1
        elif match_kind == "keyed" and not (
            body_normalized.startswith(source.normalized)
            or body_normalized.startswith(source.match_normalized)
        ):
            if body_normalized and body_normalized in source.normalized:
                trailer = ""
                counts["restored_prefixes"] += 1
            else:
                trailer = body
        else:
            consumed_normalized = (
                source.normalized
                if body_normalized.startswith(source.normalized)
                else source.match_normalized
            )
            prefix_end = body_ends[len(consumed_normalized) - 1]
            trailer = body[prefix_end:].strip()
        rendered, style = render_expression(source.text, maximum_inline_length)
        counts[style] += 1
        if trailer:
            rendered += "\n\n" + trailer
            counts["trailers"] += 1
        replacement = [""] + rendered.splitlines() + [""]
        replacements.append((section.body_start, section.body_end, replacement))

    for start, end, replacement in reversed(replacements):
        lines[start:end] = replacement

    trailing_newline = "\n" if markdown.endswith("\n") else ""
    return "\n".join(lines) + trailing_newline, counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Format explicitly headed Markdown expression sections using the "
            "line layout retained in the source PDF."
        )
    )
    parser.add_argument("source_pdf", type=Path)
    parser.add_argument("markdown", type=Path)
    parser.add_argument(
        "--inline-max",
        type=int,
        default=100,
        help="maximum length of a simple one-line expression (default: 100)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report whether safe formatting changes remain without writing",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="list Markdown expression sections that cannot be matched safely",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.inline_max < 1:
        raise SystemExit("--inline-max must be positive")
    if not args.source_pdf.is_file():
        raise SystemExit(f"Source PDF not found: {args.source_pdf}")
    if not args.markdown.is_file():
        raise SystemExit(f"Markdown file not found: {args.markdown}")

    markdown = args.markdown.read_text(encoding="utf-8")
    sources = source_expressions(args.source_pdf)
    formatted, counts = format_markdown(
        markdown, sources, args.inline_max, args.verbose
    )
    changed = formatted != markdown

    print(
        f"Expression sections: {counts['sections']} Markdown, "
        f"{counts['source']} PDF; formatted {counts['inline']} inline and "
        f"{counts['block']} as blocks; {counts['already']} already formatted; "
        f"{counts['restored_prefixes']} missing code prefixes restored; "
        f"{counts['trailers']} trailing text sections separated; "
        f"{counts['unmatched']} left unchanged; "
        f"{counts['source'] - counts['matched_source']} PDF expressions have "
        f"no matched Markdown section"
    )

    if args.check:
        if changed:
            print(f"Formatting changes are needed in {args.markdown}", file=sys.stderr)
            return 1
        return 0

    if changed:
        args.markdown.write_text(formatted, encoding="utf-8")
        print(f"Updated {args.markdown}")
    else:
        print(f"No changes needed in {args.markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
