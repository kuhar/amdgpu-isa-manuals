#!/usr/bin/env python3
"""Restore source PDF layout for pseudocode in converted ISA manuals."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import textwrap
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


EXPRESSION_HEADING = re.compile(r"^#{1,6}\s+\*\*Expression\*\*\s*$")
ANY_HEADING = re.compile(r"^#{1,6}\s+")
PAGE_FOOTER = re.compile(r"\b\d+\s+of\s+\d+$")
DOCUMENT_HEADER = re.compile(r'^.*Instruction Set Architecture$')
SOURCE_INSTRUCTION = re.compile(
    r"^\s*([A-Z][A-Z0-9_]+)\s+(\d+(?:\s*,\s*\d+)*)\s*$"
)
MARKDOWN_INSTRUCTION = re.compile(
    r"^#{2,6}\s+\*\*([A-Z][A-Z0-9_\\]+)\s+"
    r"(\d+(?:,\s*\d+)*)\*\*\s*$"
)
MARKDOWN_ESCAPES = frozenset(r"_*[]{}")
LAYOUT_EQUIVALENTS = {
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
}
CONTROL_FLOW = re.compile(
    r"(?:^|\W)(?:if|then|else|endif|for|while|do|endfor|endwhile)(?:\W|$)",
    re.IGNORECASE,
)
CODE_SIGNAL = re.compile(
    r"(?<![<>!])=(?!=)|==|!=|<=|>=|;|//|"
    r"\b(?:if|elsif|else|endif|for|endfor|while|endwhile|declare|return|break)\b",
    re.IGNORECASE,
)
LAYOUT_START_SIGNAL = re.compile(
    r"(?<![<>!])=(?!=)|==|!=|<=|>=|//|"
    r"^\s*(?:if|elsif|else|endif|for|endfor|while|endwhile|declare|return|break)\b",
    re.IGNORECASE,
)

DOCUMENT_FORMULA_FIXUPS = (
    (
        "Scalar 0-105=SGPR; 106,107=VCC, 108-123=TTMP0-15, and "
        "124-127={NULL, M0, EXEC\\_LO, EXEC\\_HI}.",
        "`Scalar 0-105=SGPR; 106,107=VCC, 108-123=TTMP0-15, and "
        "124-127={NULL, M0, EXEC_LO, EXEC_HI}.`",
    ),
    (
        "Vs = the first VGPR DWORD (start) Ve = the last VGPR DWORD (end)",
        "```text\nVs = the first VGPR DWORD (start)\n"
        "Ve = the last VGPR DWORD (end)\n```",
    ),
    (
        "OPSEL[2] = A matrix (1 = reuse, 0 = normal)",
        "`OPSEL[2] = A matrix (1 = reuse, 0 = normal)`",
    ),
    (
        "OPSEL\\_HI[2] = B matrix (1 = reuse, 0 = normal)",
        "`OPSEL_HI[2] = B matrix (1 = reuse, 0 = normal)`",
    ),
    (
        "**offset** = sgpr\\_offset + inst\\_offset + vgpr\\_offset",
        "`offset = sgpr_offset + inst_offset + vgpr_offset`",
    ),
    (
        "**total\\_offset** = index\\*stride + offset, in bytes",
        "`total_offset = index*stride + offset`, in bytes",
    ),
    (
        "Address Out-of-Range if: offset >= num\\_records",
        "Address Out-of-Range if: `offset >= num_records`",
    ),
    (
        "**GV** mem\\_addr = VGPRU64 + IOFFSETI24 **GVS** mem\\_addr = "
        "SGPRU64 + ( VGPRI32 \\* ScaleFactor ) + IOFFSETI24 **GT** "
        "mem\\_addr = SGPRU64 + IOFFSETI24 + ThreadID\\*4",
        "```text\n"
        "GV   mem_addr = VGPRU64 + IOFFSETI24\n"
        "GVS  mem_addr = SGPRU64 + (VGPRI32 * ScaleFactor) + IOFFSETI24\n"
        "GT   mem_addr = SGPRU64 + IOFFSETI24 + ThreadID*4\n"
        "```",
    ),
    (
        "**LDS** LDS\\_ADDR = VGPR\\_addrU32 + IOFFSETU16 LDS address is "
        "relative to the LDS space allocated to this wave.",
        "`LDS_ADDR = VGPR_addrU32 + IOFFSETU16`\n\n"
        "LDS address is relative to the LDS space allocated to this wave.",
    ),
    (
        "Normal (GV) addr[63:0] = VGPRU64 + IOFFSETI24",
        "Normal (GV): `addr[63:0] = VGPRU64 + IOFFSETI24`",
    ),
    (
        "GVS Mode addr[63:0] = SGPRU64 + (VGPRI32 \\* ScaleFactor) + "
        "IOFFSETI24",
        "GVS mode: `addr[63:0] = SGPRU64 + (VGPRI32 * ScaleFactor) + "
        "IOFFSETI24`",
    ),
    (
        "- GV: global\\_mem\\_addr = INST\\_OFFSET + VADDR[63:0]",
        "- GV: `global_mem_addr = INST_OFFSET + VADDR[63:0]`",
    ),
    (
        "- GVS: global\\_mem\\_addr = INST\\_OFFSET + SADDR[63:0] + "
        "VADDR[31:0]",
        "- GVS: `global_mem_addr = INST_OFFSET + SADDR[63:0] + "
        "VADDR[31:0]`",
    ),
    (
        "- bar.arrive(BarrierID)\n"
        "- phase = bar.arrive(BarrierID)\n"
        "- bar.wait(BarrierID, phase)",
        "- `bar.arrive(BarrierID)`\n"
        "- `phase = bar.arrive(BarrierID)`\n"
        "- `bar.wait(BarrierID, phase)`",
    ),
    (
        "- ds\\_permute\\_b32 : Dst[index[0..31]] = src[0..31] Where "
        "[0..31] is the lane number\n"
        "- ds\\_bpermute\\_b32 : Dst[0..31] = src[index[0..31]]",
        "- ds\\_permute\\_b32: `Dst[index[0..31]] = src[0..31]`, where "
        "`[0..31]` is the lane number\n"
        "- ds\\_bpermute\\_b32: `Dst[0..31] = src[index[0..31]]`",
    ),
    (
        "Compare operations: 1 = true Arithmetic operations: 1 = carry out "
        "Bit/logical operations: 1 = result was not zero Move: does not alter "
        "SCC",
        "```text\n"
        "Compare operations:     1 = true\n"
        "Arithmetic operations:  1 = carry out\n"
        "Bit/logical operations: 1 = result was not zero\n"
        "Move:                   does not alter SCC\n"
        "```",
    ),
    (
        "0 : Use the NV ISA bit as indication that scratch is NV or not 1 : "
        "Force threads falling into scratch to NV=1, even if ISA.NV = 0 if "
        "the address falls into scratch space (not global). This allows "
        "global.NV=0 and scratch.NV=1 for flat ops; other threads use the ISA "
        "bit value.",
        "- `0`: Use the NV ISA bit as indication that scratch is NV or not.\n"
        "- `1`: Force threads falling into scratch to `NV=1`, even if "
        "`ISA.NV=0` if the address falls into scratch space (not global). "
        "This allows `global.NV=0` and `scratch.NV=1` for flat ops; other "
        "threads use the ISA bit value.",
    ),
    (
        "SRC/DST[7] = (1=hi, 0=lo half)",
        "`SRC/DST[7] = (1=hi, 0=lo half)`",
    ),
    (
        "Concatenate the 6 VGPRs of Lane 0 {V5, V4, V3, V2, V1, V0} = "
        "{ K=31, K=30, K=29, … K=1, K=0 }.",
        "Concatenate the 6 VGPRs of Lane 0 "
        "`{V5, V4, V3, V2, V1, V0} = { K=31, K=30, K=29, … K=1, K=0 }`.",
    ),
    (
        'where "offset" is: IOFFSET + {M0 or sgpr-offset} Any DWORDs that '
        "are out of range in memory from a buffer\\_load return zero. If a "
        "multi-DWORD request (e.g. S\\_BUFFER\\_LOAD\\_B256) is partially "
        "out of range, the DWORDs that are in range return data as normal, "
        "and the out-of-range DWORDs return zero.",
        'where "offset" is: `IOFFSET + {M0 or sgpr-offset}`. Any DWORDs that '
        "are out of range in memory from a buffer\\_load return zero. If a "
        "multi-DWORD request (e.g. S\\_BUFFER\\_LOAD\\_B256) is partially "
        "out of range, the DWORDs that are in range return data as normal, "
        "and the out-of-range DWORDs return zero.",
    ),
    ("SRC0\\_MSB = SIMM16[1:0]", "`SRC0_MSB = SIMM16[1:0]`"),
    ("SRC1\\_MSB = SIMM16[3:2]", "`SRC1_MSB = SIMM16[3:2]`"),
    ("SRC2\\_MSB = SIMM16[5:4]", "`SRC2_MSB = SIMM16[5:4]`"),
    ("DST\\_MSB = SIMM16[7:6]", "`DST_MSB = SIMM16[7:6]`"),
    (
        "D0.f32 = S0.f32 \\* 2.0F \\*\\* S1.i32",
        "`D0.f32 = S0.f32 * 2.0F ** S1.i32`",
    ),
    (
        "SWAPX16 : xor\\_mask = 0x10, or\\_mask = 0x00, and\\_mask = 0x1f "
        "SWAPX8 : xor\\_mask = 0x08, or\\_mask = 0x00, and\\_mask = 0x1f "
        "SWAPX4 : xor\\_mask = 0x04, or\\_mask = 0x00, and\\_mask = 0x1f "
        "SWAPX2 : xor\\_mask = 0x02, or\\_mask = 0x00, and\\_mask = 0x1f "
        "SWAPX1 : xor\\_mask = 0x01, or\\_mask = 0x00, and\\_mask = 0x1f",
        "```text\n"
        "SWAPX16: xor_mask = 0x10, or_mask = 0x00, and_mask = 0x1f\n"
        "SWAPX8:  xor_mask = 0x08, or_mask = 0x00, and_mask = 0x1f\n"
        "SWAPX4:  xor_mask = 0x04, or_mask = 0x00, and_mask = 0x1f\n"
        "SWAPX2:  xor_mask = 0x02, or_mask = 0x00, and_mask = 0x1f\n"
        "SWAPX1:  xor_mask = 0x01, or_mask = 0x00, and_mask = 0x1f\n"
        "```",
    ),
    (
        "REVERSEX32 : xor\\_mask = 0x1f, or\\_mask = 0x00, and\\_mask = "
        "0x1f REVERSEX16 : xor\\_mask = 0x0f, or\\_mask = 0x00, and\\_mask "
        "= 0x1f REVERSEX8 : xor\\_mask = 0x07, or\\_mask = 0x00, "
        "and\\_mask = 0x1f REVERSEX4 : xor\\_mask = 0x03, or\\_mask = "
        "0x00, and\\_mask = 0x1f REVERSEX2 : xor\\_mask = 0x01 or\\_mask "
        "= 0x00, and\\_mask = 0x1f BCASTX32: xor\\_mask = 0x00, or\\_mask "
        "= thread, and\\_mask = 0x00 BCASTX16: xor\\_mask = 0x00, "
        "or\\_mask = thread, and\\_mask = 0x10 BCASTX8: xor\\_mask = 0x00, "
        "or\\_mask = thread, and\\_mask = 0x18 BCASTX4: xor\\_mask = 0x00, "
        "or\\_mask = thread, and\\_mask = 0x1c BCASTX2: xor\\_mask = 0x00, "
        "or\\_mask = thread, and\\_mask = 0x1e Pseudocode follows:",
        "```text\n"
        "REVERSEX32: xor_mask = 0x1f, or_mask = 0x00, and_mask = 0x1f\n"
        "REVERSEX16: xor_mask = 0x0f, or_mask = 0x00, and_mask = 0x1f\n"
        "REVERSEX8:  xor_mask = 0x07, or_mask = 0x00, and_mask = 0x1f\n"
        "REVERSEX4:  xor_mask = 0x03, or_mask = 0x00, and_mask = 0x1f\n"
        "REVERSEX2:  xor_mask = 0x01 or_mask = 0x00, and_mask = 0x1f\n"
        "BCASTX32:   xor_mask = 0x00, or_mask = thread, and_mask = 0x00\n"
        "BCASTX16:   xor_mask = 0x00, or_mask = thread, and_mask = 0x10\n"
        "BCASTX8:    xor_mask = 0x00, or_mask = thread, and_mask = 0x18\n"
        "BCASTX4:    xor_mask = 0x00, or_mask = thread, and_mask = 0x1c\n"
        "BCASTX2:    xor_mask = 0x00, or_mask = thread, and_mask = 0x1e\n"
        "```\n\nPseudocode follows:",
    ),
)

UNIVERSAL_DOCUMENT_FORMULA_FIXUPS = tuple(
    DOCUMENT_FORMULA_FIXUPS[index] for index in (0, 1, 14, 15, 17)
) + (
    (
        "ADDR = SGPR[base] + inst\\_offset + "
        "{ M0 or SGPR[offset] or zero } \\* 64",
        "`ADDR = SGPR[base] + inst_offset + "
        "{M0 or SGPR[offset] or zero} * 64`",
    ),
    (
        "ADDR = SGPR[base] + inst\\_offset + { M0 or SGPR[offset] or zero }",
        "`ADDR = SGPR[base] + inst_offset + {M0 or SGPR[offset] or zero}`",
    ),
    (
        "Addr = Addr - private\\_base + private\\_base\\_addr + "
        "scratch\\_baseOffset\\_for\\_this\\_wave",
        "`Addr = Addr - private_base + private_base_addr + "
        "scratch_baseOffset_for_this_wave`",
    ),
    (
        "Addr = SCRATCH\\_BASE + (offset / 4) \\* 4 \\* "
        "const\\_index\\_stride + (offset % 4) + TID\\*4 where "
        '"offset" = either "INST\\_OFFSET + SGPR\\_offset" or '
        '"INST\\_OFFSET + VGPR\\_offset".',
        "`Addr = SCRATCH_BASE + (offset / 4) * 4 * "
        "const_index_stride + (offset % 4) + TID*4`\n\n"
        "where `offset = INST_OFFSET + SGPR_offset` or "
        "`offset = INST_OFFSET + VGPR_offset`.",
    ),
    (
        "**GV** mem\\_addr = VGPRU64 + INST\\_OFFSETI13\n\n**GVS** "
        "mem\\_addr = SGPRU64 + VGPRU32 + INST\\_OFFSETI13 **GT** "
        "mem\\_addr = SGPRU64 + INST\\_OFFSETI13 + ThreadID\\*4",
        "```text\n"
        "GV   mem_addr = VGPRU64 + INST_OFFSETI13\n"
        "GVS  mem_addr = SGPRU64 + VGPRU32 + INST_OFFSETI13\n"
        "GT   mem_addr = SGPRU64 + INST_OFFSETI13 + ThreadID*4\n"
        "```",
    ),
    (
        "**GV** mem\\_addr = VGPRU64 + IOFFSETI24\n\n**GVS** mem\\_addr = "
        "SGPRU64 + VGPRU32 + IOFFSETI24 **GT** mem\\_addr = SGPRU64 + "
        "IOFFSETI24 + ThreadID\\*4",
        "```text\n"
        "GV   mem_addr = VGPRU64 + IOFFSETI24\n"
        "GVS  mem_addr = SGPRU64 + VGPRU32 + IOFFSETI24\n"
        "GT   mem_addr = SGPRU64 + IOFFSETI24 + ThreadID*4\n"
        "```",
    ),
    (
        "**LDS** LDS\\_ADDR = VGPR\\_addrU32 + INST\\_OFFSETU16",
        "`LDS_ADDR = VGPR_addrU32 + INST_OFFSETU16`",
    ),
    (
        "**LDS** LDS\\_ADDR = VGPR\\_addrU32 + IOFFSETU16",
        "`LDS_ADDR = VGPR_addrU32 + IOFFSETU16`",
    ),
    (
        "**SV** mem\\_addr = SCRATCH\\_BASEU64 + "
        "SWIZZLE(VGPR\\_offsetU32 + INST\\_OFFSETI13, ThreadID) **SS** "
        "mem\\_addr = SCRATCH\\_BASEU64 + SWIZZLE(SGPR\\_offsetU32 + "
        "INST\\_OFFSETI13, ThreadID)\n\n**SVS** mem\\_addr = "
        "SCRATCH\\_BASEU64 + SWIZZLE(SGPR\\_offsetU32 + "
        "VGPR\\_offsetU32 + INST\\_OFFSETI13, ThreadID)\n\n**ST** "
        "mem\\_addr = SCRATCH\\_BASEU64 + SWIZZLE(INST\\_OFFSETI13, "
        "ThreadID) SGPR\\_offset and VGPR\\_offset are 32 bits unsigned "
        "byte offsets.",
        "```text\n"
        "SV   mem_addr = SCRATCH_BASEU64 + "
        "SWIZZLE(VGPR_offsetU32 + INST_OFFSETI13, ThreadID)\n"
        "SS   mem_addr = SCRATCH_BASEU64 + "
        "SWIZZLE(SGPR_offsetU32 + INST_OFFSETI13, ThreadID)\n"
        "SVS  mem_addr = SCRATCH_BASEU64 + SWIZZLE(SGPR_offsetU32 + "
        "VGPR_offsetU32 + INST_OFFSETI13, ThreadID)\n"
        "ST   mem_addr = SCRATCH_BASEU64 + "
        "SWIZZLE(INST_OFFSETI13, ThreadID)\n"
        "```\n\n"
        "SGPR_offset and VGPR_offset are 32-bit unsigned byte offsets.",
    ),
    (
        "Memory[row][col] → VGPR[lane][vgpr][startPosn\\*dataSize + "
        "dataSize-1 : startPosn\\*dataSize ]",
        "`Memory[row][col] → VGPR[lane][vgpr][startPosn*dataSize + "
        "dataSize-1 : startPosn*dataSize]`",
    ),
    (
        "E.g. dataSize=8 and startPosn=2 means data is in bits: [23:16].",
        "E.g. `dataSize=8` and `startPosn=2` means data is in bits `[23:16]`.",
    ),
    (
        "Normal (GV) addr[63:0] = VGPRU64 + IOFFSETI24",
        "Normal (GV): `addr[63:0] = VGPRU64 + IOFFSETI24`",
    ),
    ("row=0..31 col=0..15", "`row=0..31 col=0..15`"),
    (
        "if (src0 == SNaN) result = QNaN (src0) else if "
        "(src1 == SNaN) result = QNaN (src1) else result = larger of "
        '(src0, src1) "Larger" order from smallest to largest: QNaN, '
        "-inf, -float, -denorm, -0, +0, +denorm, +float, +inf",
        "```text\n"
        "if (src0 == SNaN) result = QNaN (src0)\n"
        "else if (src1 == SNaN) result = QNaN (src1)\n"
        "else result = larger of (src0, src1)\n"
        '"Larger" order from smallest to largest: QNaN, -inf, -float, '
        "-denorm, -0, +0, +denorm, +float, +inf\n"
        "```",
    ),
    (
        "if (src0 == SNaN) result = QNaN (src0) else if "
        "(src1 == SNaN) result = QNaN (src1) else result = smaller of "
        '(src0, src1) "Smaller" order from smallest to largest: -inf, '
        "-float, -denorm, -0, +0, +denorm, +float, +inf, QNaN",
        "```text\n"
        "if (src0 == SNaN) result = QNaN (src0)\n"
        "else if (src1 == SNaN) result = QNaN (src1)\n"
        "else result = smaller of (src0, src1)\n"
        '"Smaller" order from smallest to largest: -inf, -float, '
        "-denorm, -0, +0, +denorm, +float, +inf, QNaN\n"
        "```",
    ),
    (
        "*FP Compare Swap: only swap if the compare condition (==) is true, "
        "treating +0 and -0 as equal* doSwap = (src0 != NaN) && "
        "(src1 != NaN) && (src0 == src1) // allow +0 == -0",
        "*FP Compare Swap: only swap if the compare condition (==) is true, "
        "treating +0 and -0 as equal*\n\n"
        "```text\n"
        "doSwap = (src0 != NaN) && (src1 != NaN) && (src0 == src1) "
        "// allow +0 == -0\n"
        "```",
    ),
    (
        "doSwap = (src0 != NaN) && (src1 != NaN) && (src0 == src1) "
        "// allow +0 == -0",
        "```text\n"
        "doSwap = (src0 != NaN) && (src1 != NaN) && (src0 == src1) "
        "// allow +0 == -0\n"
        "```",
    ),
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


@dataclass(frozen=True)
class SourceCodeBlock:
    instruction: tuple[str, str]
    text: str
    normalized: str


@dataclass(frozen=True)
class SourceLayoutBlock:
    text: str
    normalized: str


@dataclass(frozen=True)
class MarkdownInstruction:
    instruction: tuple[str, str]
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


def normalize_layout_with_ends(text: str) -> tuple[str, list[int]]:
    """Normalize document-level matches, ignoring Markdown bold markers."""
    normalized: list[str] = []
    ends: list[int] = []
    index = 0
    while index < len(text):
        if text.startswith("**", index):
            index += 2
            continue
        character = text[index]
        if (
            character == "\\"
            and index + 1 < len(text)
            and text[index + 1] in MARKDOWN_ESCAPES
        ):
            index += 1
            character = text[index]
        character = LAYOUT_EQUIVALENTS.get(character, character)
        if not character.isspace() and unicodedata.category(character) != "Cc":
            normalized.append(character)
            ends.append(index + 1)
        index += 1
    return "".join(normalized), ends


def normalize_layout(text: str) -> str:
    return normalize_layout_with_ends(text)[0]


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


def looks_like_code(text: str, normalized: str) -> bool:
    """Reject indented tables, bullets, and prose surrounding pseudocode."""
    if len(normalized) < 12:
        return False
    if text.lstrip().startswith(("•", "Table ", "where:", "Reserved")):
        return False
    return bool(CODE_SIGNAL.search(text))


def looks_like_layout_code(text: str, normalized: str) -> bool:
    """Reject monospace page fragments with a long prose lead-in."""
    if not looks_like_code(text, normalized):
        return False
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    first_signal = next(
        (
            index
            for index, line in enumerate(lines)
            if LAYOUT_START_SIGNAL.search(line)
        ),
        len(lines),
    )
    return first_signal <= 1


def looks_like_instruction_code(text: str, normalized: str) -> bool:
    """Accept short operations when a mnemonic and opcode constrain matching."""
    if len(normalized) < 5:
        return False
    if text.lstrip().startswith(("•", "Table ", "where:", "Reserved")):
        return False
    return bool(CODE_SIGNAL.search(text))


def source_instruction_blocks(pdf: Path) -> list[SourceCodeBlock]:
    """Extract code-like indented blocks from unheaded instruction entries."""
    lines = pdf_text(pdf).splitlines()
    headers: list[tuple[int, tuple[str, str]]] = []
    for index, line in enumerate(lines):
        match = SOURCE_INSTRUCTION.fullmatch(line)
        if not match or match.start(2) < 20:
            continue
        headers.append(
            (
                index,
                (match.group(1), re.sub(r"\s+", "", match.group(2))),
            )
        )

    blocks: list[SourceCodeBlock] = []
    seen: set[tuple[tuple[str, str], str]] = set()
    for header_index, (start, instruction) in enumerate(headers):
        end = (
            headers[header_index + 1][0]
            if header_index + 1 < len(headers)
            else len(lines)
        )
        index = start + 1
        while index < end:
            if (
                not lines[index].strip()
                or not lines[index][:1].isspace()
                or is_page_furniture(lines[index])
            ):
                index += 1
                continue

            body: list[str] = []
            while index < end:
                if (
                    lines[index].strip()
                    and lines[index][:1].isspace()
                    and not is_page_furniture(lines[index])
                ):
                    body.append(lines[index].rstrip())
                    index += 1
                    continue

                lookahead = index
                crossed_page = False
                while lookahead < end and (
                    not lines[lookahead].strip()
                    or is_page_furniture(lines[lookahead])
                ):
                    crossed_page |= is_page_furniture(lines[lookahead])
                    lookahead += 1
                if (
                    crossed_page
                    and lookahead < end
                    and lines[lookahead][:1].isspace()
                ):
                    index = lookahead
                    continue
                break

            text = textwrap.dedent("\n".join(body)).strip()
            normalized = normalize(text)
            key = (instruction, normalized)
            if (
                normalized
                and key not in seen
                and looks_like_instruction_code(text, normalized)
            ):
                blocks.append(SourceCodeBlock(instruction, text, normalized))
                seen.add(key)
    return blocks


def source_layout_blocks(pdf: Path) -> list[SourceLayoutBlock]:
    """Extract code-like blocks identified by the PDF's monospace font."""
    try:
        completed = subprocess.run(
            [
                "pdftohtml",
                "-xml",
                "-hidden",
                "-i",
                "-stdout",
                str(pdf),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as error:
        raise SystemExit(
            "pdftohtml is required; install the Poppler command-line tools"
        ) from error
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or f"exit status {error.returncode}"
        raise SystemExit(f"pdftohtml failed: {detail}") from error

    try:
        root = ET.fromstring(completed.stdout)
    except ET.ParseError as error:
        raise SystemExit(f"pdftohtml emitted invalid XML: {error}") from error

    blocks: list[SourceLayoutBlock] = []
    seen: set[str] = set()
    font_families: dict[str, str] = {}
    for page in root.findall("page"):
        for font in page.findall("fontspec"):
            font_families[font.attrib["id"]] = font.attrib.get("family", "")

        fragments: dict[int, list[tuple[int, int, int, str]]] = {}
        for element in page.findall("text"):
            family = font_families.get(element.attrib.get("font", ""), "")
            if "RobotoMono" not in family:
                continue
            text = "".join(element.itertext()).replace("\xa0", " ")
            if not text.strip():
                continue
            top = int(element.attrib["top"])
            fragments.setdefault(top, []).append(
                (
                    int(element.attrib["left"]),
                    int(element.attrib["width"]),
                    int(element.attrib["height"]),
                    text,
                )
            )

        lines: list[tuple[int, int, str]] = []
        for top, pieces in sorted(fragments.items()):
            pieces.sort()
            line = pieces[0][3]
            previous_right = pieces[0][0] + pieces[0][1]
            heights = [pieces[0][2]]
            for left, width, height, fragment in pieces[1:]:
                gap = max(0, left - previous_right)
                character_width = max(1.0, width / max(1, len(fragment)))
                line += " " * max(1, round(gap / character_width)) + fragment
                previous_right = left + width
                heights.append(height)
            lines.append((top, max(heights), line.rstrip()))

        page_blocks: list[list[str]] = []
        current: list[str] = []
        previous_top = 0
        previous_height = 0
        for top, height, line in lines:
            gap = top - previous_top if current else 0
            if current and gap > max(previous_height, height) * 2.5:
                page_blocks.append(current)
                current = []
            elif current and gap > max(previous_height, height) * 1.55:
                current.append("")
            current.append(line)
            previous_top = top
            previous_height = height
        if current:
            page_blocks.append(current)

        for body in page_blocks:
            text = textwrap.dedent("\n".join(body)).strip("\n").rstrip()
            text = "".join(
                LAYOUT_EQUIVALENTS.get(character, character)
                for character in text
            )
            normalized = normalize_layout(text)
            if (
                normalized
                and normalized not in seen
                and looks_like_layout_code(text, normalized)
            ):
                blocks.append(SourceLayoutBlock(text, normalized))
                seen.add(normalized)
    return blocks


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


def markdown_instructions(lines: list[str]) -> list[MarkdownInstruction]:
    headings: list[tuple[int, tuple[str, str]]] = []
    for index, line in enumerate(lines):
        match = MARKDOWN_INSTRUCTION.fullmatch(line)
        if not match:
            continue
        headings.append(
            (
                index,
                (
                    match.group(1).replace("\\", ""),
                    re.sub(r"\s+", "", match.group(2)),
                ),
            )
        )

    instructions: list[MarkdownInstruction] = []
    for heading_index, (start, instruction) in enumerate(headings):
        end = (
            headings[heading_index + 1][0]
            if heading_index + 1 < len(headings)
            else len(lines)
        )
        instructions.append(
            MarkdownInstruction(instruction, start, start + 1, end, start + 1)
        )
    return instructions


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


def formatted_code(body: str) -> str | None:
    """Return code from one protected inline span or fenced block."""
    parts = formatted_parts(body)
    if parts is None:
        return None
    code, trailer = parts
    return code if not trailer else None


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
    return "\n".join(lines).rstrip("\n") + trailing_newline, counts


def formatted_ranges(markdown: str) -> list[tuple[int, int]]:
    """Locate existing fenced and inline code in a Markdown fragment."""
    ranges = [
        match.span()
        for match in re.finditer(
            r"(?ms)^(`{3,})[^\n]*\n.*?^\1[ \t]*$", markdown
        )
    ]
    ranges.extend(
        match.span()
        for match in re.finditer(r"(?<!`)`[^`\n]+`(?!`)", markdown)
        if not any(
            start <= match.start() and match.end() <= end
            for start, end in ranges
        )
    )
    return ranges


def table_ranges(markdown: str) -> list[tuple[int, int]]:
    """Locate Markdown table rows, where inserting block markup is unsafe."""
    return [
        match.span()
        for match in re.finditer(r"(?m)^\|.*\|[ \t]*$", markdown)
    ]


def heading_ranges(markdown: str) -> list[tuple[int, int]]:
    """Locate Markdown headings, which document-level matches must not alter."""
    return [
        match.span()
        for match in re.finditer(r"(?m)^#{1,6}[ \t]+.*$", markdown)
    ]


def find_all(text: str, fragment: str) -> list[int]:
    starts: list[int] = []
    start = 0
    while fragment and (found := text.find(fragment, start)) >= 0:
        starts.append(found)
        start = found + len(fragment)
    return starts


def format_unheaded_markdown(
    markdown: str,
    sources: list[SourceCodeBlock],
    maximum_inline_length: int,
    verbose: bool,
) -> tuple[str, dict[str, int]]:
    """Format exact PDF code matches inside unheaded instruction entries."""
    lines = markdown.splitlines()
    instructions = markdown_instructions(lines)
    by_instruction: dict[tuple[str, str], list[SourceCodeBlock]] = {}
    for source in sources:
        by_instruction.setdefault(source.instruction, []).append(source)

    replacements: list[tuple[int, int, list[str]]] = []
    counts = {
        "instructions": len(instructions),
        "source_blocks": len(sources),
        "matched": 0,
        "inline": 0,
        "block": 0,
        "already": 0,
        "restored_prefixes": 0,
        "restored_suffixes": 0,
        "table_skipped": 0,
        "unmatched_instructions": 0,
    }

    for instruction in instructions:
        candidates = by_instruction.get(instruction.instruction, [])
        if not candidates:
            continue
        body = "\n".join(lines[instruction.body_start : instruction.body_end])
        body_normalized, body_ends = normalize_with_ends(body)
        existing_ranges = formatted_ranges(body)
        protected_tables = table_ranges(body)
        occupied: list[tuple[int, int]] = []
        claimed_raw: list[tuple[int, int]] = []
        body_replacements: list[tuple[int, int, str]] = []
        unique_candidates = {
            source.normalized: source for source in candidates
        }.values()

        existing_code = []
        for start, end in existing_ranges:
            code = formatted_code(body[start:end])
            if code is not None:
                existing_code.append((start, end, normalize(code)))
        joined_existing_code = "".join(
            normalized for _, _, normalized in existing_code
        )

        for source in sorted(
            unique_candidates,
            key=lambda candidate: len(candidate.normalized),
            reverse=True,
        ):
            # Earlier conversions sometimes retained only one side of an
            # instruction body split by a page boundary. Restore the complete
            # source block only when an existing code span is an exact proper
            # prefix or suffix of the PDF block for the same mnemonic and
            # opcode. Joining all existing code first avoids duplicating a
            # block that Markdown merely split into separate fences.
            suffix_matches = [
                (start, end, normalized)
                for start, end, normalized in existing_code
                if normalized
                and len(source.normalized) > len(normalized)
                and source.normalized.endswith(normalized)
                and source.normalized not in joined_existing_code
                and not any(
                    start < claimed_end and end > claimed_start
                    for claimed_start, claimed_end in claimed_raw
                )
            ]
            if suffix_matches:
                raw_start, raw_end, _ = max(
                    suffix_matches, key=lambda match: len(match[2])
                )
                rendered, style = render_expression(
                    source.text, maximum_inline_length
                )
                body_replacements.append((raw_start, raw_end, rendered))
                claimed_raw.append((raw_start, raw_end))
                counts["matched"] += 1
                counts[style] += 1
                counts["restored_prefixes"] += 1
                continue

            prefix_matches = [
                (start, end, normalized)
                for start, end, normalized in existing_code
                if normalized
                and len(source.normalized) > len(normalized)
                and source.normalized.startswith(normalized)
                and source.normalized not in joined_existing_code
                and not any(
                    start < claimed_end and end > claimed_start
                    for claimed_start, claimed_end in claimed_raw
                )
            ]
            if prefix_matches:
                raw_start, raw_end, _ = max(
                    prefix_matches, key=lambda match: len(match[2])
                )
                rendered, style = render_expression(
                    source.text, maximum_inline_length
                )
                body_replacements.append((raw_start, raw_end, rendered))
                claimed_raw.append((raw_start, raw_end))
                counts["matched"] += 1
                counts[style] += 1
                counts["restored_suffixes"] += 1
                continue

            for normalized_start in find_all(
                body_normalized, source.normalized
            ):
                normalized_end = normalized_start + len(source.normalized)
                if any(
                    normalized_start < end and normalized_end > start
                    for start, end in occupied
                ):
                    continue
                raw_start = (
                    body_ends[normalized_start - 1]
                    if normalized_start
                    else 0
                )
                raw_end = body_ends[normalized_end - 1]
                if any(
                    raw_start < claimed_end and raw_end > claimed_start
                    for claimed_start, claimed_end in claimed_raw
                ):
                    continue
                occupied.append((normalized_start, normalized_end))
                if any(
                    raw_start < end and raw_end > start
                    for start, end in protected_tables
                ):
                    counts["table_skipped"] += 1
                    continue
                counts["matched"] += 1
                if any(
                    start <= raw_start and raw_end <= end
                    for start, end in existing_ranges
                ):
                    counts["already"] += 1
                    continue
                rendered, style = render_expression(
                    source.text, maximum_inline_length
                )
                counts[style] += 1
                body_replacements.append((raw_start, raw_end, rendered))

        if not occupied and not body_replacements:
            counts["unmatched_instructions"] += 1
            if verbose:
                name, opcode = instruction.instruction
                print(
                    f"No source code match for {name} {opcode} at Markdown "
                    f"line {instruction.line_number}",
                    file=sys.stderr,
                )
            continue
        if not body_replacements:
            continue

        for start, end, rendered in sorted(body_replacements, reverse=True):
            prefix = body[:start].rstrip()
            suffix = body[end:].lstrip()
            body = prefix
            if body:
                body += "\n\n"
            body += rendered
            if suffix:
                body += "\n\n" + suffix
        replacement = [""] + body.strip().splitlines() + [""]
        replacements.append(
            (instruction.body_start, instruction.body_end, replacement)
        )

    for start, end, replacement in reversed(replacements):
        lines[start:end] = replacement

    trailing_newline = "\n" if markdown.endswith("\n") else ""
    return "\n".join(lines).rstrip("\n") + trailing_newline, counts


def format_layout_markdown(
    markdown: str,
    sources: list[SourceLayoutBlock],
    maximum_inline_length: int,
) -> tuple[str, dict[str, int]]:
    """Format exact source-layout matches anywhere outside Markdown tables."""
    body_normalized, body_ends = normalize_layout_with_ends(markdown)
    existing_ranges = formatted_ranges(markdown)
    protected_tables = table_ranges(markdown)
    protected_headings = heading_ranges(markdown)
    occupied: list[tuple[int, int]] = []
    replacements: list[tuple[int, int, str]] = []
    counts = {
        "source_blocks": len(sources),
        "matched": 0,
        "inline": 0,
        "block": 0,
        "already": 0,
        "table_skipped": 0,
    }

    for source in sorted(
        sources, key=lambda candidate: len(candidate.normalized), reverse=True
    ):
        for normalized_start in find_all(body_normalized, source.normalized):
            normalized_end = normalized_start + len(source.normalized)
            if any(
                normalized_start < end and normalized_end > start
                for start, end in occupied
            ):
                continue
            raw_start = body_ends[normalized_start] - 1
            if (
                raw_start > 0
                and markdown[raw_start - 1] == "\\"
                and markdown[raw_start] in MARKDOWN_ESCAPES
            ):
                raw_start -= 1
            raw_end = body_ends[normalized_end - 1]
            if markdown[max(0, raw_start - 2) : raw_start] == "**":
                raw_start -= 2
            if markdown[raw_end : raw_end + 2] == "**":
                raw_end += 2
            occupied.append((normalized_start, normalized_end))
            if any(
                raw_start < end and raw_end > start
                for start, end in protected_tables + protected_headings
            ):
                counts["table_skipped"] += 1
                continue
            counts["matched"] += 1
            if any(
                start <= raw_start and raw_end <= end
                for start, end in existing_ranges
            ):
                counts["already"] += 1
                continue
            rendered, style = render_expression(
                source.text, maximum_inline_length
            )
            counts[style] += 1
            replacements.append((raw_start, raw_end, rendered))

    for start, end, rendered in sorted(replacements, reverse=True):
        prefix = markdown[:start].rstrip()
        suffix = markdown[end:].lstrip()
        markdown = prefix
        if markdown:
            markdown += "\n\n"
        markdown += rendered
        if suffix:
            markdown += "\n\n" + suffix

    trailing_newline = "\n" if markdown.endswith("\n") else ""
    return markdown.rstrip("\n") + trailing_newline, counts


def apply_document_formula_fixups(
    markdown: str,
    fixups: tuple[tuple[str, str], ...] = DOCUMENT_FORMULA_FIXUPS,
) -> tuple[str, int]:
    """Apply conservative, reviewed formula splits outside source code fonts."""
    count = 0
    for original, replacement in fixups:
        if replacement in markdown:
            continue
        matches = markdown.count(original)
        if matches:
            markdown = markdown.replace(original, replacement)
            count += matches
    return markdown, count


def merge_continuation_fences(markdown: str) -> tuple[str, int]:
    """Join adjacent code fences when the second starts mid-control-flow."""
    lines = markdown.splitlines()
    opener = re.compile(r"^(`{3,})(?:text)?[ \t]*$")
    continuation = re.compile(
        r"^(?:elsif\b|else\b|endif\b|}\s*(?:elsif|else)\b)", re.I
    )
    fence: str | None = None
    index = 0
    count = 0
    while index < len(lines):
        line = lines[index]
        if fence is None:
            match = opener.fullmatch(line)
            if match:
                fence = match.group(1)
            index += 1
            continue
        if line != fence:
            index += 1
            continue

        next_open = index + 1
        while next_open < len(lines) and not lines[next_open].strip():
            next_open += 1
        match = opener.fullmatch(lines[next_open]) if next_open < len(lines) else None
        if not match:
            fence = None
            index += 1
            continue

        first_code = next_open + 1
        while first_code < len(lines) and not lines[first_code].strip():
            first_code += 1
        if (
            first_code < len(lines)
            and continuation.match(lines[first_code].strip())
        ):
            del lines[index : next_open + 1]
            count += 1
            continue

        fence = None
        index += 1

    trailing_newline = "\n" if markdown.endswith("\n") else ""
    return "\n".join(lines) + trailing_newline, count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Format Markdown instruction pseudocode using the line layout "
            "retained in the source PDF."
        )
    )
    parser.add_argument("source_pdf", type=Path)
    parser.add_argument("markdown", type=Path)
    parser.add_argument(
        "--mode",
        choices=("auto", "headed", "unheaded"),
        default="auto",
        help=(
            "select explicit Expression sections or unheaded instruction "
            "entries (default: auto)"
        ),
    )
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
    mode = args.mode
    if mode == "auto":
        mode = (
            "headed"
            if markdown_expressions(markdown.splitlines())
            else "unheaded"
        )

    if mode == "headed":
        sources = source_expressions(args.source_pdf)
        formatted, counts = format_markdown(
            markdown, sources, args.inline_max, args.verbose
        )
    else:
        source_blocks = source_instruction_blocks(args.source_pdf)
        formatted, counts = format_unheaded_markdown(
            markdown, source_blocks, args.inline_max, args.verbose
        )

    # Instruction-section matching handles the bulk of the operations, while
    # the source font catches formulas and pseudocode elsewhere in the manual.
    # Tables and headings remain protected by format_layout_markdown().
    layout_sources = source_layout_blocks(args.source_pdf)
    formatted, layout_counts = format_layout_markdown(
        formatted, layout_sources, args.inline_max
    )
    fixups = (
        DOCUMENT_FORMULA_FIXUPS
        if mode == "headed"
        else UNIVERSAL_DOCUMENT_FORMULA_FIXUPS
    )
    formatted, layout_counts["formula_fixups"] = (
        apply_document_formula_fixups(formatted, fixups)
    )
    if mode == "unheaded":
        formatted, layout_counts["continuation_merges"] = (
            merge_continuation_fences(formatted)
        )
    else:
        layout_counts["continuation_merges"] = 0
    changed = formatted != markdown

    if mode == "headed":
        print(
            f"Expression sections: {counts['sections']} Markdown, "
            f"{counts['source']} PDF; formatted {counts['inline']} inline and "
            f"{counts['block']} as blocks; {counts['already']} already "
            f"formatted; {counts['restored_prefixes']} missing code prefixes "
            f"restored; {counts['trailers']} trailing text sections separated; "
            f"{counts['unmatched']} left unchanged; "
            f"{counts['source'] - counts['matched_source']} PDF expressions "
            f"have no matched Markdown section; document layout matched "
            f"{layout_counts['matched']} of {layout_counts['source_blocks']} "
            f"code-like PDF blocks, formatted {layout_counts['inline']} inline "
            f"and {layout_counts['block']} as blocks, with "
            f"{layout_counts['already']} already formatted and "
            f"{layout_counts['table_skipped']} table or heading matches "
            f"preserved; applied {layout_counts['formula_fixups']} reviewed "
            f"formula fixups; merged "
            f"{layout_counts['continuation_merges']} continuation fences"
        )
    else:
        print(
            f"Instruction entries: {counts['instructions']} Markdown, "
            f"{counts['source_blocks']} code-like PDF blocks; matched "
            f"{counts['matched']}; formatted {counts['inline']} inline and "
            f"{counts['block']} as blocks; {counts['already']} already "
            f"formatted; {counts['restored_prefixes']} missing code prefixes "
            f"and {counts['restored_suffixes']} missing code suffixes restored; "
            f"{counts['table_skipped']} table matches preserved; "
            f"{counts['unmatched_instructions']} instruction entries with "
            f"source code but no exact Markdown match; document layout "
            f"matched {layout_counts['matched']} of "
            f"{layout_counts['source_blocks']} code-like PDF blocks, "
            f"formatted {layout_counts['inline']} inline and "
            f"{layout_counts['block']} as blocks, with "
            f"{layout_counts['already']} already formatted and "
            f"{layout_counts['table_skipped']} table or heading matches "
            f"preserved; applied {layout_counts['formula_fixups']} reviewed "
            f"formula fixups; merged "
            f"{layout_counts['continuation_merges']} continuation fences"
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
