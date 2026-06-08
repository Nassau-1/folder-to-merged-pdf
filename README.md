# Folder To Merged PDF

Small Windows-first utility that:

- scans a folder recursively
- converts supported Office files to PDF with LibreOffice
- merges the PDFs into one file
- adds a footer showing the original relative file path
- optionally anonymizes terms in the merged PDF

## Current Scope: Version 1

Version 1 is intentionally narrow:

- it treats PDF as the main interchange format
- it converts supported Office files to PDF before processing
- it merges many files into one reviewable PDF
- it supports explicit text replacement on text-based PDFs

This makes V1 useful for:

- reducing document-count friction during upload
- creating a single review file from a folder tree
- applying basic, user-supplied anonymization pairs

It does **not** try to produce a semantically structured output for LLM ingestion.
It also does **not** reliably handle scanned pages, embedded images, complex tables,
multi-column reading order, repeated watermarks, or automatic named-entity
anonymization.

## Supported Inputs

- `.pdf`
- `.doc`
- `.docx`
- `.ppt`
- `.pptx`

## Requirements

- Python 3.10+
- LibreOffice installed
- `soffice` available on `PATH`, or `LIBREOFFICE_PATH` set to the full path of `soffice.exe`

Install Python dependencies:

```powershell
py -m pip install -r requirements.txt
```

## Basic Usage

Interactive mode:

```powershell
py .\folder_to_merged_pdf.py
```

Non-interactive mode:

```powershell
py .\folder_to_merged_pdf.py "C:\Path\To\Data Room" -o "C:\Path\merged.pdf"
```

With anonymization:

```powershell
py .\folder_to_merged_pdf.py "C:\Path\To\Data Room" `
  -o "C:\Path\merged.pdf" `
  --replace "CompanyName=Project Alpha" `
  --replace "Client X=Customer 01"
```

With a pairs file:

```powershell
py .\folder_to_merged_pdf.py "C:\Path\To\Data Room" --pairs-file .\pairs.txt
```

Example `pairs.txt`:

```text
CompanyName -> Project Alpha
Client X = Customer 01
```

## Notes

- Merge order is deterministic: alphabetical by relative path.
- Footer text always uses relative paths, never absolute drive paths.
- If one Office file fails to convert, the rest of the run continues.
- If one PDF fails during page processing, that file is skipped without partially merging it.
- Anonymization only works on real text in PDFs, not on scanned images.

## Next Direction: Version 2 Roadmap

The likely long-term direction for this project is **not** "better PDF merging".
The better target is a local, client-side document preparation pipeline that turns
mixed source files into a format that is safer, cleaner, and more intelligible for
LLMs before upload.

### V2 Goal

Build a local document normalization and anonymization tool that:

- ingests folders containing mixed business documents
- preserves document structure better than naive text extraction
- produces LLM-ready outputs such as Markdown and structured JSON
- detects likely sensitive entities and repetitive noise automatically
- keeps a human review step before destructive replacements

### Why V2 Should Move Beyond a Single Merged PDF

A single merged PDF helped with upload-count constraints, but it has major limits:

- PDF is not the best working format for downstream language-model analysis
- merged PDFs lose semantic structure across files
- layout-heavy pages are difficult to parse correctly later
- anonymization at the PDF layer is fragile when text is image-based
- repeated watermarks and boilerplate waste context tokens

V2 should treat PDF as one possible input, not as the canonical output.

### Proposed V2 Output Package

For each processing run, the tool should ideally generate a normalized output bundle
rather than one monolithic file. A candidate structure:

```text
output/
  manifest.json
  documents/
    0001_source-document.md
    0001_source-document.blocks.json
    0002_source-document.md
  entities/
    detected_entities.csv
    replacement_plan.json
  assets/
    0001_page_01.png
    0001_figure_02.png
  review/
    warnings.json
    processing_report.md
```

Suggested roles:

- `manifest.json`: run metadata, source file list, hashes, language guesses, pipeline status
- `*.md`: reading-order-preserving text for LLM upload
- `*.blocks.json`: structural representation of titles, paragraphs, tables, figures, page references, bounding boxes
- `detected_entities.csv`: candidate names, organizations, emails, domains, labels, frequencies, confidence
- `replacement_plan.json`: approved anonymization mapping
- `warnings.json`: OCR uncertainty, unreadable pages, likely parsing errors, ambiguous entities

### Core V2 Pipeline

The expected processing pipeline should be roughly:

1. Discover and classify input files.
2. Extract native text when available.
3. Run OCR only where native text is absent or clearly insufficient.
4. Recover layout and reading order.
5. Detect tables, headers, footers, and repeated watermarks.
6. Detect candidate sensitive entities.
7. Present a reviewable anonymization plan.
8. Apply approved transformations.
9. Export LLM-ready text plus structured metadata.

### Extraction Strategy

V2 should prefer the richest source available per document type:

- text-native PDFs: parse text objects and layout metadata first
- scanned PDFs: OCR with page-level confidence reporting
- DOCX: extract semantic structure directly when possible
- PPTX: extract slide text, notes, and object positions where useful
- spreadsheets: likely out of scope for the first V2 milestone unless explicitly added

Important principle:

- prefer native extraction over OCR
- use OCR as fallback, not as the default path

### Layout and Reading Order

This is one of the main reasons to build V2.

The tool should avoid naive left-to-right raw text dumps and instead attempt to
preserve:

- multi-column reading order
- page sections and headings
- table boundaries
- bullet and numbered list structure
- caption-to-figure relationships
- page breaks and source references

At a minimum, the extraction layer should preserve enough block metadata to support:

- reconstructing Markdown in a stable reading order
- reviewing whether a page was parsed incorrectly
- re-running only the affected documents later

### Table Handling

Tables should not be flattened blindly into prose when structure matters.

V2 should aim to:

- detect table regions separately from body text
- preserve row and column boundaries where possible
- export tables into structured JSON or Markdown tables when safe
- attach a warning when confidence is low or merged cells make reconstruction unreliable

### Image, Figure, and Chart Handling

V1 effectively ignores non-text content except as part of the PDF surface.
V2 should explicitly track visual content, even if interpretation remains limited.

Desired behavior:

- identify pages or regions containing figures, charts, or diagrams
- extract image assets when useful
- reference those assets from the structured output
- avoid pretending that a figure was fully converted into faithful text when it was not

This project does not need full chart understanding in the first iteration, but it
should leave room for future captioning or multimodal review.

### Automatic Anonymization Strategy

A simple word-frequency script is useful, but not sufficient on its own.
The practical V2 approach should combine several heuristics:

- stopword filtering for at least French and English
- casing heuristics
- repeated uncommon token detection
- named-entity recognition for people, companies, locations, products, funds, and emails
- regex-based detection for domains, phone numbers, identifiers, and watermark patterns
- document-level frequency scoring
- cross-document consistency for the same entity within one run

The output should separate:

- `detected candidate`
- `suggested replacement`
- `approved replacement`

That keeps the system useful without making unsafe automatic edits by default.

### Watermark and Boilerplate Removal

This is a high-value V2 capability.

The tool should try to detect and optionally suppress:

- repeated confidentiality banners
- repeated recipient lines
- repeated email addresses in page backgrounds
- repeated headers and footers that add little semantic value

Detection can start with simple heuristics:

- exact repeated strings across many pages
- repeated tokens at similar page coordinates
- high-frequency lines with low semantic diversity

### Human Review Model

V2 should keep a review step before final anonymized export.

Recommended review flow:

1. run extraction and candidate detection
2. generate a review file with proposed entities and repeated boilerplate
3. allow accept/edit/reject decisions
4. produce the final cleaned export

This can begin as a file-based review workflow before any GUI exists.

### Suggested Implementation Phases

#### Phase 0: Architecture and Fixtures

- define the normalized output schema
- create a representative fixture set of sample documents
- separate pure pipeline code from any future UI
- add regression fixtures for multi-column PDFs, scans, tables, and watermark-heavy pages

#### Phase 1: Structured Extraction

- replace the "merge to one PDF" mindset with per-document normalized export
- add Markdown output
- add block-level JSON output
- preserve page and source references

#### Phase 2: OCR and Layout Recovery

- add OCR fallback for scanned pages
- add reading-order reconstruction
- add table-region detection
- emit confidence and warnings

#### Phase 3: Entity Detection and Anonymization Review

- detect candidate names and identifiers automatically
- produce a reviewable replacement plan
- support deterministic replacement across the whole run

#### Phase 4: Boilerplate and Watermark Suppression

- detect repeated page-level noise
- allow safe removal or exclusion from LLM-ready exports

#### Phase 5: Optional UX Layer

- add a local UI or guided CLI workflow
- allow side-by-side review of source page and extracted text
- allow manual correction before export

### Non-Goals for the First V2 Iteration

To keep V2 tractable, the first milestone should probably **not** attempt all of the
following:

- perfect OCR on every scan quality level
- full visual reasoning over charts and diagrams
- fully automatic anonymization without review
- support for every Office and archive format from day one
- cloud-dependent processing as a hard requirement

### Suggested Technical Direction

The exact stack can change, but the architecture should likely favor:

- Python as the orchestration language
- modular extractors by file type
- a normalized intermediate representation before export
- deterministic, testable transforms
- local-first processing

Likely categories of components:

- document parsers
- OCR engine adapter
- layout analyzer
- entity detector
- replacement engine
- export renderers
- review artifact generator

### Practical Success Criteria for an Initial V2

An initial V2 should be considered successful if it can reliably do the following on
a small but realistic fixture set:

- process a folder of mixed PDFs and DOCX files locally
- preserve reading order on common two-column pages better than raw extraction
- emit readable Markdown and structured JSON
- detect obvious organization names, person names, emails, and repeated watermarks
- generate a reviewable anonymization plan
- produce a final cleaned export that is more LLM-ready than the original files

### Handoff Note for the Next Implementation Pass

The next implementation pass should begin by defining the intermediate document schema
and creating fixture-based tests before choosing UI details. The first serious V2 work
should optimize for correctness, inspectability, and deterministic outputs rather than
for packaging or interface polish.

## Build Artifact Hygiene

`build/` and `dist/` are generated outputs and are intentionally excluded from git.

If you want to ship a Windows executable, keep using the existing `folder_to_merged_pdf.spec` file and build it separately from the source repo.
