# Converting ISA manuals to Markdown

This repository stores each manual as:

- `<family>/README.md` for the rendered text;
- `<family>/<source-name>_meta.json` for Marker metadata; and
- `<family>/assets/*.jpeg` for the retained technical figures.

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
JSON file, and JPEGs. Import it using the repository layout:

1. Copy the generated Markdown to `<family>/README.md`.
2. Prepend the repository notice shown below, replacing `SOURCE_URL` with the
   verified direct PDF URL.
3. Copy the metadata JSON without renaming it.
4. Create `<family>/assets/` and copy only retained images there.
5. Rewrite Markdown image targets from `_page_...jpeg` to
   `assets/_page_...jpeg`.

Keep the notice before the converted title so that it cannot be mistaken for
part of AMD's publication:

```markdown
> **Repository notice (not part of the AMD publication).** This is an unofficial Markdown conversion of the [AMD source PDF](SOURCE_URL), produced with automated tooling for easier browsing and text search. It is not affiliated with or endorsed by AMD and may contain errors and omissions. AMD retains its rights in the underlying publication; AMD's own agreement, disclaimer, and copyright and trademark notices are reproduced below. Consult the linked PDF as the authoritative version.
```

The reference rewrite is mechanical:

```sh
family=cdna5
sed -i -E \
  's@\]\((_page_[^)]*\.jpeg)\)@](assets/\1)@g' \
  "$family/README.md"
```

Then perform a visual image audit. Marker classifications are heuristic, so do
not delete every file named `Picture` without looking at it.

- Remove decorative callout icons, isolated footnote numbers, page logos, and
  other fragments that do not convey manual content. Remove their Markdown
  references at the same time.
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
- Known limitation: broader multi-page table and instruction-heading losses
  require systematic source-aware repair rather than isolated hand edits

The pinned CPU stack and the TheRock-backed CPU run produced byte-identical
Markdown and JPEGs on the 54-page smoke sample. Metadata differed only in
sub-pixel floating-point polygon coordinates, which is why the committed full
metadata is generated with the pinned CPU environment above.
