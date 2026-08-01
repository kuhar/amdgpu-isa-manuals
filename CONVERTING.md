# Converting AMD architecture publications to Markdown

This repository stores each ISA manual as:

- `<family>/README.md` for the rendered text;
- `<family>/<source-name>_meta.json` for Marker metadata; and
- `<family>/assets/*.jpeg` for the retained technical figures.

When an official architecture white paper is available, it is stored beside
the ISA manual as:

- `<family>/whitepaper.md` for the rendered text;
- `<family>/whitepaper_meta.json` for Marker metadata; and
- `<family>/whitepaper-assets/*.jpeg` for retained technical figures.

The original manuals were imported with Marker in commit `8328861`, renamed to
`README.md` in `097dab5`, moved under `assets/` in `7ac375e`, and cleaned of
repeated page furniture and decorative images in `a6c3838`.

## Pinned conversion environment

The current workflow was validated with CPython 3.12.3 and the following
CPU-only stack. Keep the versions pinned: layout-model changes can alter
headings, tables, image boundaries, and metadata coordinates.

```sh
marker_env=/tmp/amdgpu-isa-marker-2.0.0

uv venv --python 3.12.3 "$marker_env"
uv pip install \
  --python "$marker_env/bin/python" \
  --torch-backend cpu \
  'marker-pdf==2.0.0' \
  'surya-ocr==0.22.1' \
  'torch==2.13.0+cpu' \
  'torchvision==0.28.0+cpu' \
  'pdftext==0.7.1' \
  'pypdfium2==5.10.1' \
  'transformers==5.14.1' \
  'numpy==2.5.1' \
  'pillow==10.4.0'
```

Apply the repository's two Marker 2.0 adjustments before converting an older
ISA manual. The first reconstructs explicitly headed tables from their printed
column geometry, rejoins wrapped mnemonic suffixes, and retains continuation
lines as blank-key rows. The second preserves literal `|` operators inside
Markdown tables as HTML entities instead of deleting them.

```sh
marker_site=$(
  "$marker_env/bin/python" -c \
    'import site; print(site.getsitepackages()[0])'
)

patch -d "$marker_site" -p1 < marker-2.0-table-reconstruction.patch
patch -d "$marker_site" -p1 < marker-2.0-markdown-tables.patch
```

Both patches apply to the pinned `marker-pdf==2.0.0` package. A failed hunk is
a signal to re-audit the new package rather than forcing the old adjustment.

Marker 2 has separate `balanced` and `fast` paths. AMD's ISA PDFs have a good
embedded text layer, so use `fast` with OCR disabled. This uses the lightweight
layout detector and PDF text/table extraction without starting the Surya VLM
server.

```sh
manual_slug=amd-instinct-cdna5-instruction-set-architecture
manual_pdf=/tmp/$manual_slug.pdf
conversion_out=/tmp/amdgpu-isa-marker-output

TORCH_DEVICE=cpu FAST_DETECTOR_DEVICE=cpu \
  "$marker_env/bin/marker_single" "$manual_pdf" \
  --mode fast \
  --disable_ocr \
  --output_dir "$conversion_out"
```

Do not use `--disable_ocr` without checking the PDF. If pages are scanned or
their embedded text is corrupt, test a small page range with OCR enabled and
inspect the result before converting the whole document.

### GPU status

As of 2026-07-31, the production multi-architecture TheRock/PyTorch nightly
(`torch 2.14.0a0+rocm7.15.0a20260721`) passed numeric dispatch on both `gfx1201`
and `gfx1100`. Marker 2.0 was not usable through that GPU path:

- balanced mode treated PyTorch's ROCm `cuda` device as NVIDIA and tried to
  launch the NVIDIA vLLM container; and
- fast mode failed in Surya's DINO layout backbone with a HIP invalid-argument
  error on both GPUs.

Use the pinned CPU path until a newer Marker/Surya release passes a
representative conversion on ROCm. A simple `torch.arange` smoke test is not
sufficient; exercise the layout model before selecting the GPU path.

## Download and verify the source

Record the public source URL, byte size, page count, and SHA-256 digest in the
change description or in a conversion record below. `wget` has been more
reliable than `curl` against the AMD document server.

Use a URL that returns the PDF itself. Some older human-readable AMD `.pdf`
URLs now redirect to a document landing page; in that case, follow the page's
PDF link and record the resulting direct `docs.amd.com/api/.../content` URL.
After downloading, confirm that the first-page title and publication date match
the Markdown being imported. Matching only the architecture family is not
sufficient because AMD can publish a newer revision at the same landing page.

```sh
manual_url=https://www.amd.com/content/dam/amd/en/documents/instinct-tech-docs/instruction-set-architectures/amd-instinct-cdna5-instruction-set-architecture.pdf
manual_slug=amd-instinct-cdna5-instruction-set-architecture
manual_pdf=/tmp/$manual_slug.pdf

wget --user-agent='Mozilla/5.0' -O "$manual_pdf" "$manual_url"
printf '%s  %s\n' \
  '5fae9822405c04f3e380c38d55b27df5b19469b78d5dfdd87c319a712f0239a8' \
  "$manual_pdf" | sha256sum --check -
file "$manual_pdf"
pdfinfo "$manual_pdf"
```

## Smoke test before the full conversion

Choose pages that cover the front matter, normal prose, complex tables,
technical figures, instruction definitions, and the end of the document. For
CDNA5, the following 54-page sample was used:

```sh
smoke_out=/tmp/amdgpu-isa-marker-smoke

TORCH_DEVICE=cpu FAST_DETECTOR_DEVICE=cpu \
  "$marker_env/bin/marker_single" "$manual_pdf" \
  --mode fast \
  --disable_ocr \
  --page_range '0-15,37-40,100,400,800-831' \
  --output_dir "$smoke_out"
```

Inspect the Markdown and every extracted image before starting the full run.
The smoke test should also confirm that repeated headers, footers, and page
numbers are absent.

## Import and cleanup

Marker writes a nested directory containing one Markdown file, one metadata
JSON file, and JPEGs. Import it with `scripts/prepare-marker-output.py`:

```sh
family=cdna5
metadata_name=amd-instinct-cdna5-instruction-set-architecture_meta.json

./scripts/prepare-marker-output.py \
  "$conversion_out/$manual_slug" \
  "$family" \
  --slug "$manual_slug" \
  --metadata-name "$metadata_name" \
  --source-url "$manual_url"
```

The preparation script performs these mechanical steps:

1. Copy the generated Markdown to the selected Markdown filename (by default,
   `<family>/README.md`).
2. Prepend the repository notice shown below, replacing `SOURCE_URL` with the
   verified direct PDF URL.
3. Copy the metadata JSON to the requested repository filename.
4. Recreate the selected assets directory (by default, `<family>/assets/`)
   with retained technical images.
5. Rewrite Markdown image targets from `_page_...jpeg` to the selected assets
   directory.
6. Remove the known decorative `Picture` fragments and same-page byte-identical
   image duplicates emitted by these manuals.
7. Join blank-key table continuation rows to the preceding keyed row, including
   when the PDF page boundary created two adjacent Markdown table blocks, and
   combine adjacent table fragments that repeat the same column headings.
8. Link each contents-table entry to the corresponding explicit page anchor.
   The script reports entries whose headings or anchors require manual repair.

For prose-style manuals, restore the source pseudocode layout after importing:

```sh
./scripts/format-manual-expressions.py \
  "$manual_pdf" \
  "$family/README.md"
```

This pass uses Poppler's `pdftotext -layout` output as the source of line
breaks and indentation for instruction expressions. For document-level code
throughout the manuals, it also uses `pdftohtml -xml` font metadata. The
checked ISA PDFs mark pseudocode with Roboto Mono, while ordinary prose usually
uses a proportional face. Some older publications also use the monospace face
for explanatory text, so a candidate must contain an assignment, comparison,
comment, or control-flow keyword by its second non-empty line. This avoids
treating long indented prose fragments as code.

The pass automatically handles explicitly labelled `Expression` sections, as
in CDNA5; unlabelled pseudocode between instruction entries, as in CDNA3/4 and
RDNA3/3.5/4; and monospace pseudocode elsewhere in every manual. A simple
expression of at most 100 characters is wrapped in inline code; multiline,
control-flow, comment-bearing, and longer expressions use fenced `text`
blocks. Markdown escapes inside matched code are removed because code spans
and blocks display those characters literally.

Matching uses the instruction mnemonic and opcode when they are available,
with document order and normalized source text as fallbacks. In explicitly
labelled manuals, prose accidentally joined to an expression at a page
boundary is moved below the code block, and exact source-suffix matches restore
dropped code prefixes. In unlabelled manuals, only exact normalized source
matches inside the corresponding instruction entry are changed. If an older
conversion retained only one side of a page-spanning instruction body, the
complete block is restored only when the existing code is an exact proper
prefix or suffix of the PDF block for the same mnemonic and opcode.
Document-level matches are also exact, and Markdown tables, headings, existing
code spans, and existing fences are protected. Monospace blocks split by a
printed page boundary remain separate fenced blocks unless the next fragment
begins with an unambiguous continuation token such as `elsif`, `endif`, or
`} else`; those fragments are joined automatically. Sections that cannot be
matched are reported and left unchanged for source comparison. The command is
idempotent; use `--verbose` to list unmatched sections.

Reviewed exact fixups cover recurring formulas printed in a proportional font,
including register maps, address calculations, matrix-index notation,
floating-point selection rules, and permute notation. Keep these patterns in
the formatter so a fresh conversion reproduces the Markdown cleanup.

CDNA1/2, RDNA1/2, and the Vega manuals use a different publication layout:
operations are already isolated in a dedicated Markdown table column. Do not
run block formatting inside those cells because fenced blocks would break the
table structure. The formatter still handles document-level pseudocode outside
those tables and protects every table row.

For a white paper, select the alternate filenames and notice explicitly. The
repeatable `--skip-image` option records images rejected during the visual
audit and prevents them from being copied or referenced:

```sh
family=cdna5
whitepaper_slug=cdna5-whitepaper
whitepaper_url=https://www.amd.com/content/dam/amd/en/documents/products/technologies/cdna/amd-cdna5-whitepaper.pdf

./scripts/prepare-marker-output.py \
  "$conversion_out/$whitepaper_slug" \
  "$family" \
  --slug "$whitepaper_slug" \
  --document-type whitepaper \
  --markdown-name whitepaper.md \
  --metadata-name whitepaper_meta.json \
  --assets-name whitepaper-assets \
  --source-url "$whitepaper_url" \
  --skip-image _page_2_Picture_3.jpeg \
  --skip-image _page_4_Diagram_5.jpeg \
  --skip-image _page_15_Diagram_5.jpeg
```

Keep the notice before the converted title so that it cannot be mistaken for
part of AMD's publication:

```markdown
> **Repository notice (not part of the AMD publication).** This is an unofficial Markdown conversion of the [AMD source PDF](SOURCE_URL), produced with automated tooling for easier browsing and text search. It is not affiliated with or endorsed by AMD and may contain errors and omissions. AMD retains its rights in the underlying publication; AMD's own agreement, disclaimer, and copyright and trademark notices are reproduced below. Consult the linked PDF as the authoritative version.
```

Then perform a visual image audit. Marker classifications are heuristic, so
confirm that the preparation script's size rule did not remove a technical
figure or retain a decorative fragment.

- Remove decorative callout icons, isolated footnote numbers, page logos, and
  other fragments that do not convey manual content. Remove their Markdown
  references at the same time.
- For white papers, retain architecture topology, chip/package, compute-block,
  data-path, cache/memory, partitioning, and interconnect diagrams. Product or
  rack renders are optional when the surrounding text carries the same
  information. Remove cover art, decorative backgrounds, repeated page strips,
  website screenshots, and redundant product photography.
- Find byte-identical images with SHA-256. When Marker emits adjacent `Figure`
  and `Diagram` references for the same bytes, retain one reference and one
  file. Prefer the `Figure` name for consistency with older imports.
- Keep real architecture diagrams and encoding figures even when they appear
  only once.

```sh
find "$family/assets" -type f -name '*.jpeg' -print0 \
  | xargs -0 sha256sum \
  | sort
```

Marker 2 removed the CDNA5 page furniture automatically. For future manuals,
search for the document title, copyright line, company address, section title,
and `N of M` page-number forms. Repeated matches require page-by-page review;
avoid broad text deletion because the same strings can be legitimate content.

## Validation

At minimum, validate all of the following:

```sh
family=cdna5
manual_slug=amd-instinct-cdna5-instruction-set-architecture

jq empty "$family/${manual_slug}_meta.json"
jq '{pages: (.page_stats | length), methods: [.page_stats[].text_extraction_method] | unique}' \
  "$family/${manual_slug}_meta.json"

rg -o '!\[[^]]*\]\(assets/[^)]*\)' "$family/README.md" \
  | sed -E 's/^!\[[^]]*\]\(([^)]*)\)$/\1/' \
  | sort > /tmp/amdgpu-isa-referenced-images.txt
uniq -d /tmp/amdgpu-isa-referenced-images.txt
uniq /tmp/amdgpu-isa-referenced-images.txt \
  > /tmp/amdgpu-isa-unique-referenced-images.txt
find "$family/assets" -type f -name '*.jpeg' -printf '%p\n' \
  | sed "s#^$family/##" \
  | sort -u > /tmp/amdgpu-isa-present-images.txt
comm -3 \
  /tmp/amdgpu-isa-unique-referenced-images.txt \
  /tmp/amdgpu-isa-present-images.txt

find "$family/assets" -type f -name '*.jpeg' -print0 \
  | xargs -0 sha256sum \
  | sort \
  | awk 'seen[$1]++ { print }'

rg -n -U '^#### \*\*Expression\*\*\n\n(?:####|#)' "$family/README.md"

./scripts/format-manual-expressions.py \
  "$manual_pdf" \
  "$family/README.md" \
  --check \
  --verbose

rg -o 'id="[^"]+"' "$family/README.md" \
  | sed -E 's/^id="(.*)"$/\1/' \
  | sort -u > /tmp/amdgpu-isa-anchors.txt
rg -o '\]\(#[^)]+\)' "$family/README.md" \
  | sed -E 's/^\]\(#([^)]*)\)$/\1/' \
  | sort -u > /tmp/amdgpu-isa-internal-targets.txt
comm -23 /tmp/amdgpu-isa-internal-targets.txt /tmp/amdgpu-isa-anchors.txt

git add "$family" CONVERTING.md
git diff --cached --check
git status --short
```

The duplicate-reference check, `comm -3`, duplicate-image check, empty-
expression search, internal-target check, and staged whitespace check should
print nothing. If `CONVERTING.md` is unchanged, omit it from `git add`. Also
compare the metadata page count with `pdfinfo`, inspect the first and last
sections, and spot-check several instruction tables and expressions against the
source PDF. Check both sides of PDF page boundaries: headings, expression
bodies, and table rows are especially prone to being separated there.

## CDNA5 conversion record

- Source title: `"CDNA5" Instruction Set Architecture: Reference Guide`
- Source date: 27-July-2026
- Source size: 3,596,954 bytes
- Source pages: 832
- Source SHA-256:
  `5fae9822405c04f3e380c38d55b27df5b19469b78d5dfdd87c319a712f0239a8`
- Marker page extraction: 832 of 832 pages used `pdftext`
- Tables: 337 total, 281 reconstructed directly from PDF text
- Raw images: 29
- Removed during cleanup: 14 decorative fragments and three duplicate copies
- Retained technical images: 12
- Audit repairs: three instruction headings, 14 expression bodies, two
  expression labels, six small table structures, and several front-matter page
  splits
- Expression formatting: all 1,445 explicitly headed sections formatted; 527
  simple expressions rendered as inline code, 918 rendered as source-indented
  code blocks, and 22 missing code prefixes restored from exact source-suffix
  matches. A source-font pass additionally restored 138 inline and 232 fenced
  pseudocode fragments outside those sections, including addressing formulas,
  examples, and unlabelled instruction expressions. Twenty-seven reviewed
  Markdown-side fixups format short formulas whose PDF source uses the prose
  font but whose assignment or control syntax is unambiguous.
- Known limitation: broader multi-page table and instruction-heading losses
  require systematic source-aware repair rather than isolated hand edits; 171
  PDF expressions do not have a corresponding explicit Markdown section

The pinned CPU stack and the TheRock-backed CPU run produced byte-identical
Markdown and JPEGs on the 54-page smoke sample. Metadata differed only in
sub-pixel floating-point polygon coordinates, which is why the committed full
metadata is generated with the pinned CPU environment above.

## Prose-style expression formatting records

The unlabelled manuals were formatted from exact source-text matches. The
"unchanged" column counts instruction entries for which the PDF contained a
code-like candidate but the Markdown did not contain an exact normalized
match; these entries were preserved for source comparison. Matches inside
Markdown tables are also counted separately and preserved.

| Family  | Matched source blocks | New inline spans | New fenced blocks | Existing formatted blocks | Protected table matches | Unchanged entries |
|---------|----------------------:|-----------------:|------------------:|--------------------------:|------------------------:|------------------:|
| CDNA3   | 1,414                 | 309              | 951               | 154                       | 13                      | 84                |
| CDNA4   | 1,489                 | 325              | 979               | 185                       | 14                      | 93                |
| RDNA3   | 1,300                 | 388              | 658               | 254                       | 0                       | 70                |
| RDNA3.5 | 1,394                 | 481              | 783               | 130                       | 0                       | 71                |
| RDNA4   | 1,450                 | 480              | 837               | 133                       | 0                       | 97                |

## Document-level pseudocode formatting records

The source-font pass was applied repository-wide on 2026-08-01. These are net
new Markdown constructs relative to the instruction-expression formatting
commits that preceded the pass. A smaller fence count than the formatter's
initial report means adjacent page fragments were verified as one logical block
and consolidated.

| Family  | New inline spans | New fenced blocks |
|---------|-----------------:|------------------:|
| CDNA1   | 5                | 11                |
| CDNA2   | 6                | 12                |
| CDNA3   | 19               | 50                |
| CDNA4   | 16               | 52                |
| RDNA1   | 9                | 8                 |
| RDNA2   | 7                | 9                 |
| RDNA3   | 29               | 59                |
| RDNA3.5 | 13               | 50                |
| RDNA4   | 19               | 89                |
| Vega    | 6                | 9                 |
| Vega 7  | 6                | 9                 |

## White paper conversion records

All five white papers were converted on 2026-08-01 with the pinned Marker 2.0
CPU workflow. Every page used the embedded `pdftext` layer. The files named
under "excluded images" are repeatable `--skip-image` arguments; they capture
the visual audit rather than an automatic Marker classification.

### CDNA 1

- Source: `amd-cdna-white-paper.pdf`
- Source size: 3,379,915 bytes
- Source pages: 11
- Source SHA-256:
  `d62f13d68fe57f6878d18ee896a18342d3343481f83372fce8f87fb3eb48e959`
- Raw images: 7
- Retained technical images: 6
- Excluded images: `_page_0_Picture_4.jpeg` (cover visual)

### CDNA 2

- Source: `amd-cdna2-white-paper.pdf`
- Source size: 1,788,074 bytes
- Source pages: 17
- Source SHA-256:
  `62125a4a3f00e653556ca98c178712496b241e5c3d8a4edadee7578944c2cc6d`
- Raw images: 9
- Retained technical images: 8
- Excluded images: `_page_12_Picture_6.jpeg` (website screenshot)

### CDNA 3

- Source: `amd-cdna-3-white-paper.pdf`
- Source size: 8,096,236 bytes
- Source pages: 28
- Source SHA-256:
  `a0811d04f101f9127bd183d6e228f462b6fd988b0e0e6d263a25e4bed712f593`
- Raw images: 13
- Retained technical images: 10
- Excluded images: `_page_0_Picture_0.jpeg`,
  `_page_8_Picture_0.jpeg`, and `_page_25_Picture_0.jpeg` (cover art and
  decorative page strips)

### CDNA 4

- Source: `amd-cdna-4-architecture-whitepaper.pdf`
- Source size: 2,703,210 bytes
- Source pages: 21
- Source SHA-256:
  `7ebf89edb9b82198b9edea7bb37eb7fe7c998842257eb21ef7a459a87774a4b2`
- Raw images: 16
- Retained technical images: 5
- Excluded images: `_page_0_Picture_0.jpeg`, `_page_5_Diagram_5.jpeg`,
  `_page_6_Picture_0.jpeg`, `_page_8_Picture_0.jpeg`,
  `_page_9_Diagram_4.jpeg`, `_page_12_Picture_0.jpeg`,
  `_page_14_Picture_0.jpeg`, `_page_15_Picture_0.jpeg`,
  `_page_16_Picture_0.jpeg`, `_page_17_Picture_0.jpeg`, and
  `_page_20_Picture_0.jpeg` (cover art, duplicate crops, and decorative page
  strips)

### CDNA 5

- Source: `amd-cdna5-whitepaper.pdf`
- Source size: 4,152,251 bytes
- Source pages: 24
- Source SHA-256:
  `2381d60185f79989d3d5e4260c86f72504fcab256b40bb85fe4a6dd782afb3ef`
- Raw images: 13
- Retained technical images: 10
- Excluded images: `_page_2_Picture_3.jpeg` (product render),
  `_page_4_Diagram_5.jpeg` (duplicate crop), and
  `_page_15_Diagram_5.jpeg` (full-rack product image)
