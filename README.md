# AMD GPU architecture publications in Markdown

> **Repository notice.** This repository contains unofficial Markdown conversions of AMD instruction set architecture manuals and architecture white papers, produced with automated tooling for easier browsing and text search. It is not affiliated with or endorsed by AMD, and the conversions may contain errors and omissions. AMD retains its rights in the underlying publications; agreements, disclaimers, and copyright and trademark notices present in the sources are reproduced with the conversions and should be read before relying on or redistributing the converted text. Each conversion links to its AMD source PDF, which is the authoritative version.

## CDNA manuals

- [CDNA 1 — AMD Instinct MI100](cdna1/)
- [CDNA 2 — AMD Instinct MI200](cdna2/)
- [CDNA 3 — AMD Instinct MI300](cdna3/)
- [CDNA 4 — AMD Instinct MI350 series](cdna4/)
- [CDNA 5 — AMD Instinct MI400 series](cdna5/)

## RDNA manuals

- [RDNA 1](rdna1/)
- [RDNA 2](rdna2/)
- [RDNA 3](rdna3/)
- [RDNA 3.5](rdna3.5/)
- [RDNA 4](rdna4/)

## Vega manuals

- [Vega](vega/)
- [Vega 7 nm](vega7/)

## Official supporting material

### Architecture white papers

Only architectures with a currently reachable official AMD white paper are
listed here.

- CDNA 1: [Markdown](cdna1/whitepaper.md) · [AMD source PDF](https://www.amd.com/content/dam/amd/en/documents/instinct-business-docs/white-papers/amd-cdna-white-paper.pdf)
- CDNA 2: [Markdown](cdna2/whitepaper.md) · [AMD source PDF](https://www.amd.com/content/dam/amd/en/documents/instinct-business-docs/white-papers/amd-cdna2-white-paper.pdf)
- CDNA 3: [Markdown](cdna3/whitepaper.md) · [AMD source PDF](https://www.amd.com/content/dam/amd/en/documents/instinct-tech-docs/white-papers/amd-cdna-3-white-paper.pdf)
- CDNA 4: [Markdown](cdna4/whitepaper.md) · [AMD source PDF](https://www.amd.com/content/dam/amd/en/documents/instinct-tech-docs/white-papers/amd-cdna-4-architecture-whitepaper.pdf)
- CDNA 5: [Markdown](cdna5/whitepaper.md) · [AMD source PDF](https://www.amd.com/content/dam/amd/en/documents/products/technologies/cdna/amd-cdna5-whitepaper.pdf)
- [AMD GPU architecture documentation index](https://rocm.docs.amd.com/en/latest/reference/gpu-arch/index.html)

### Machine-readable ISA specifications

AMD currently provides XML specifications for CDNA 1–4 and RDNA 1–4,
including RDNA 3.5:

- [Documentation and supported architectures](https://gpuopen.com/machine-readable-isa/)
- [Latest XML specification bundle](https://gpuopen.com/download/machine-readable-isa/latest/)
- [XML schema documentation](https://github.com/GPUOpen-Tools/isa_spec_manager/blob/main/documentation/spec_documentation.md)
- [ISA specification tools and decoder](https://github.com/GPUOpen-Tools/isa_spec_manager)

See [CONVERTING.md](CONVERTING.md) for the conversion, cleanup, and validation workflow.
