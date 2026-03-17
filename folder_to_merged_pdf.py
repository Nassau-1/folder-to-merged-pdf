from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import tempfile
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

import fitz  # PyMuPDF
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas


SUPPORTED_OFFICE_EXTS = {".doc", ".docx", ".ppt", ".pptx"}
SUPPORTED_PDF_EXTS = {".pdf"}
SUPPORTED_EXTS = SUPPORTED_PDF_EXTS | SUPPORTED_OFFICE_EXTS
DEFAULT_OUTPUT_NAME = "merged_documents.pdf"
DEFAULT_SUFFIX = "_anon"
LIBREOFFICE_ENV_VAR = "LIBREOFFICE_PATH"


@dataclass(frozen=True)
class ReplacementPair:
    original: str
    replacement: str


@dataclass(frozen=True)
class Document:
    absolute_path: Path
    relative_path: Path


@dataclass
class MergeStats:
    discovered_documents: int = 0
    converted_documents: int = 0
    merged_documents: int = 0
    total_pages: int = 0
    skipped_documents: list[tuple[str, str]] = field(default_factory=list)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Recursively scan a folder, convert supported Office documents to PDF "
            "with LibreOffice, merge everything into one PDF, and optionally "
            "anonymize specific terms."
        )
    )
    parser.add_argument(
        "root_folder",
        nargs="?",
        help="Root folder to scan recursively.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help=(
            "Output PDF path. Defaults to '<root_folder>\\merged_documents.pdf'."
        ),
    )
    parser.add_argument(
        "--replace",
        action="append",
        default=[],
        metavar="ORIGINAL=REPLACEMENT",
        help=(
            "Replacement pair for anonymization. May be supplied multiple times. "
            "Also accepts 'original -> replacement'."
        ),
    )
    parser.add_argument(
        "--pairs-file",
        help=(
            "Text file containing anonymization pairs, one per line, using either "
            "'original=replacement' or 'original -> replacement'."
        ),
    )
    parser.add_argument(
        "--suffix",
        default=DEFAULT_SUFFIX,
        help="Suffix for the anonymized output file. Default: _anon",
    )
    parser.add_argument(
        "--no-footer",
        action="store_true",
        help="Skip the per-page relative-path footer overlay.",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Fail instead of prompting when required values are missing.",
    )
    parser.add_argument(
        "--no-pause",
        action="store_true",
        help="Do not wait for Enter before closing when run interactively.",
    )
    return parser


def parse_pair_line(line: str) -> ReplacementPair:
    text = line.strip()
    if not text:
        raise ValueError("Replacement line cannot be empty.")

    for separator in ("->", "="):
        if separator in text:
            original, replacement = [part.strip() for part in text.split(separator, 1)]
            if original and replacement:
                return ReplacementPair(original=original, replacement=replacement)
            break

    raise ValueError(
        "Expected replacement in the form 'original -> replacement' or "
        "'original=replacement'."
    )


def normalize_directory(path_text: str) -> Path:
    path = Path(path_text.strip().strip('"')).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"'{path}' is not a valid directory.")
    return path


def normalize_output_path(path_text: str, root_folder: Path) -> Path:
    if path_text.strip():
        output_path = Path(path_text.strip().strip('"')).expanduser()
    else:
        output_path = root_folder / DEFAULT_OUTPUT_NAME

    if output_path.suffix.lower() != ".pdf":
        output_path = output_path.with_suffix(".pdf")

    return output_path.resolve()


def ask_folder_path() -> Path:
    while True:
        print("Enter the path of the root folder containing your documents:")
        value = input("> ").strip()
        if not value:
            print("A folder path is required.")
            continue
        try:
            return normalize_directory(value)
        except ValueError as exc:
            print(f"Error: {exc}")


def ask_output_path(root_folder: Path) -> Path:
    default_output = root_folder / DEFAULT_OUTPUT_NAME
    print(
        f"Enter the output PDF path "
        f"(press Enter to use default: {default_output})"
    )
    value = input("> ").strip()
    return normalize_output_path(value, root_folder)


def ask_anonymization_pairs() -> list[ReplacementPair]:
    print(
        "\nDo you want to anonymize words "
        "(for example 'CompanyName' -> 'Project Hepta')? [y/N]"
    )
    answer = input("> ").strip().lower()
    if answer not in {"y", "yes"}:
        return []

    print(
        "\nEnter anonymization pairs, one per line, in the form:\n"
        "original -> replacement\n"
        "Example: eleQtron -> Project QuBit\n"
        "Press Enter on an empty line when you are done.\n"
    )

    pairs: list[ReplacementPair] = []
    while True:
        line = input().strip()
        if not line:
            break
        try:
            pairs.append(parse_pair_line(line))
        except ValueError as exc:
            print(f"  Invalid format: {exc}")

    if pairs:
        print("\nAnonymization pairs loaded:")
        for pair in pairs:
            print(f"  '{pair.original}' -> '{pair.replacement}'")
    else:
        print("No anonymization pairs specified.")

    return pairs


def load_pairs_from_file(path_text: str) -> list[ReplacementPair]:
    pairs_path = Path(path_text).expanduser().resolve()
    if not pairs_path.is_file():
        raise FileNotFoundError(f"Pairs file not found: {pairs_path}")

    pairs: list[ReplacementPair] = []
    for line_number, raw_line in enumerate(
        pairs_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            pairs.append(parse_pair_line(stripped))
        except ValueError as exc:
            raise ValueError(f"{pairs_path}:{line_number}: {exc}") from exc

    return pairs


def resolve_runtime_inputs(
    args: argparse.Namespace,
) -> tuple[Path, Path, list[ReplacementPair]]:
    interactive = sys.stdin.isatty() and not args.non_interactive

    if args.root_folder:
        root_folder = normalize_directory(args.root_folder)
    elif interactive:
        root_folder = ask_folder_path()
    else:
        raise ValueError("root_folder is required in non-interactive mode.")

    if args.output:
        output_path = normalize_output_path(args.output, root_folder)
    elif interactive:
        output_path = ask_output_path(root_folder)
    else:
        output_path = normalize_output_path("", root_folder)

    pairs: list[ReplacementPair] = []
    for raw_pair in args.replace:
        pairs.append(parse_pair_line(raw_pair))
    if args.pairs_file:
        pairs.extend(load_pairs_from_file(args.pairs_file))
    if not pairs and interactive:
        pairs = ask_anonymization_pairs()

    return root_folder, output_path, deduplicate_pairs(pairs)


def deduplicate_pairs(pairs: Sequence[ReplacementPair]) -> list[ReplacementPair]:
    deduped: list[ReplacementPair] = []
    seen: set[tuple[str, str]] = set()
    for pair in pairs:
        key = (pair.original, pair.replacement)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(pair)
    return deduped


def find_documents(root_folder: Path) -> list[Document]:
    documents: list[Document] = []
    for dirpath, dirnames, filenames in os.walk(root_folder):
        dirnames.sort()
        filenames.sort()
        for name in filenames:
            extension = Path(name).suffix.lower()
            if extension not in SUPPORTED_EXTS:
                continue
            absolute_path = Path(dirpath, name)
            relative_path = absolute_path.relative_to(root_folder)
            documents.append(
                Document(
                    absolute_path=absolute_path,
                    relative_path=relative_path,
                )
            )
    return documents


def convert_with_libreoffice(input_path: Path, output_dir: Path) -> Path:
    soffice_path = os.environ.get(LIBREOFFICE_ENV_VAR, "soffice")
    command = [
        soffice_path,
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(output_dir),
        str(input_path),
    ]

    print(f"Converting to PDF using LibreOffice: {input_path.name}")
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "LibreOffice 'soffice' executable not found. Install LibreOffice and "
            "ensure 'soffice' is on PATH, or set the LIBREOFFICE_PATH "
            "environment variable."
        ) from exc

    if result.returncode != 0:
        raise RuntimeError(
            f"LibreOffice conversion failed for '{input_path}':\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )

    pdf_path = output_dir / f"{input_path.stem}.pdf"
    if not pdf_path.exists():
        raise RuntimeError(
            f"Expected converted PDF not found after conversion: {pdf_path}"
        )
    return pdf_path


def convert_all_to_pdfs(
    documents: Sequence[Document],
    temp_root: Path,
) -> tuple[list[Document], int, list[tuple[str, str]]]:
    pdf_documents: list[Document] = []
    skipped_documents: list[tuple[str, str]] = []
    converted_count = 0

    for document in documents:
        extension = document.absolute_path.suffix.lower()
        if extension in SUPPORTED_PDF_EXTS:
            pdf_documents.append(document)
            continue

        output_dir = temp_root / document.relative_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            pdf_path = convert_with_libreoffice(document.absolute_path, output_dir)
        except RuntimeError as exc:
            message = str(exc)
            print(f"[WARN] Skipping '{document.relative_path}': {message}")
            skipped_documents.append((document.relative_path.as_posix(), message))
            continue

        pdf_documents.append(
            Document(
                absolute_path=pdf_path,
                relative_path=document.relative_path,
            )
        )
        converted_count += 1

    pdf_documents.sort(key=lambda item: item.relative_path.as_posix())
    return pdf_documents, converted_count, skipped_documents


def create_footer_overlay(
    footer_text: str,
    page_width: float,
    page_height: float,
):
    max_chars = 180
    if len(footer_text) > max_chars:
        footer_text = "..." + footer_text[-max_chars:]

    packet = io.BytesIO()
    pdf_canvas = canvas.Canvas(packet, pagesize=(page_width, page_height))
    pdf_canvas.setFont("Helvetica", 7)
    pdf_canvas.drawString(36, 18, footer_text)
    pdf_canvas.save()
    packet.seek(0)
    return PdfReader(packet).pages[0]


def build_pages_for_document(
    pdf_path: Path,
    footer_text: str,
    add_footer: bool,
):
    reader = PdfReader(str(pdf_path))
    processed_pages = []

    for page_index, page in enumerate(reader.pages, start=1):
        try:
            if add_footer:
                mediabox = page.mediabox
                overlay_page = create_footer_overlay(
                    footer_text=footer_text,
                    page_width=float(mediabox.width),
                    page_height=float(mediabox.height),
                )
                page.merge_page(overlay_page)
            processed_pages.append(page)
        except Exception as exc:
            raise RuntimeError(
                f"page {page_index} could not be processed: {exc}"
            ) from exc

    return processed_pages


def merge_pdfs(
    pdf_documents: Sequence[Document],
    output_path: Path,
    add_footer: bool,
) -> MergeStats:
    writer = PdfWriter()
    stats = MergeStats(discovered_documents=len(pdf_documents))

    for document in pdf_documents:
        relative_path = document.relative_path.as_posix()
        print(f"Adding '{relative_path}'")

        try:
            pages = build_pages_for_document(
                pdf_path=document.absolute_path,
                footer_text=relative_path,
                add_footer=add_footer,
            )
        except Exception as exc:
            message = str(exc)
            print(f"[WARN] Skipping '{relative_path}': {message}")
            stats.skipped_documents.append((relative_path, message))
            continue

        for page in pages:
            writer.add_page(page)

        stats.merged_documents += 1
        stats.total_pages += len(pages)

    if stats.total_pages == 0:
        raise RuntimeError("No pages could be merged.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as file_handle:
        writer.write(file_handle)

    return stats


def add_suffix_to_filename(path: Path, suffix: str) -> Path:
    actual_suffix = suffix or DEFAULT_SUFFIX
    if not actual_suffix.startswith("_"):
        actual_suffix = f"_{actual_suffix}"
    return path.with_name(f"{path.stem}{actual_suffix}{path.suffix or '.pdf'}")


def anonymize_pdf(
    input_path: Path,
    output_path: Path,
    pairs: Sequence[ReplacementPair],
) -> int:
    if not pairs:
        return 0

    print("\nApplying anonymization on merged PDF...")
    document = fitz.open(str(input_path))
    total_hits = 0

    try:
        for page in document:
            page_hits = 0
            for pair in pairs:
                rects = page.search_for(pair.original)
                for rect in rects:
                    page.add_redact_annot(
                        rect,
                        text=pair.replacement,
                        fill=(1, 1, 1),
                    )
                    page_hits += 1
            if page_hits:
                page.apply_redactions()
                total_hits += page_hits

        document.save(str(output_path), garbage=4, deflate=True)
    finally:
        document.close()

    return total_hits


def print_summary(
    output_path: Path,
    final_path: Path,
    pairs: Sequence[ReplacementPair],
    stats: MergeStats,
) -> None:
    print(f"\nDone. Wrote {stats.total_pages} pages to '{output_path}'.")
    print(
        "Summary: "
        f"{stats.merged_documents} merged file(s), "
        f"{stats.converted_documents} converted via LibreOffice, "
        f"{len(stats.skipped_documents)} skipped."
    )

    if stats.skipped_documents:
        print("\nSkipped files:")
        for relative_path, error in stats.skipped_documents:
            print(f" - {relative_path}: {error[:200]}")

    if pairs:
        print(f"\nFinal anonymized output: '{final_path}'")
    else:
        print(f"\nFinal output file: '{final_path}'")


def run(
    root_folder: Path,
    output_path: Path,
    pairs: Sequence[ReplacementPair],
    add_footer: bool,
    anonymized_suffix: str,
) -> Path:
    print("=== Folder to merged PDF ===\n")
    print(f"Root folder: {root_folder}")
    print(f"Output path: {output_path}")

    documents = find_documents(root_folder)
    if not documents:
        raise RuntimeError("No supported documents were found.")

    print(f"\nScanning folder... found {len(documents)} supported document(s).")
    with tempfile.TemporaryDirectory(prefix="folder2pdf_") as temp_dir:
        pdf_documents, converted_count, skipped_during_conversion = convert_all_to_pdfs(
            documents=documents,
            temp_root=Path(temp_dir),
        )

        if not pdf_documents:
            raise RuntimeError("No PDFs were available after conversion.")

        print(f"Merging {len(pdf_documents)} PDF(s) into a single file...")
        stats = merge_pdfs(
            pdf_documents=pdf_documents,
            output_path=output_path,
            add_footer=add_footer,
        )
        stats.discovered_documents = len(documents)
        stats.converted_documents = converted_count
        stats.skipped_documents = (
            skipped_during_conversion + stats.skipped_documents
        )

    if pairs:
        anonymized_output_path = add_suffix_to_filename(output_path, anonymized_suffix)
        replacements = anonymize_pdf(
            input_path=output_path,
            output_path=anonymized_output_path,
            pairs=pairs,
        )
        if replacements == 0:
            print("No occurrences were found for the supplied replacement pairs.")
        else:
            print(
                f"Anonymized PDF written to '{anonymized_output_path}' "
                f"with {replacements} replacement(s)."
            )
        final_path = anonymized_output_path
    else:
        final_path = output_path

    print_summary(output_path=output_path, final_path=final_path, pairs=pairs, stats=stats)
    return final_path


def should_pause_on_exit(args: argparse.Namespace) -> bool:
    return (
        sys.stdin.isatty()
        and sys.stdout.isatty()
        and len(sys.argv) == 1
        and not args.no_pause
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        root_folder, output_path, pairs = resolve_runtime_inputs(args)
        run(
            root_folder=root_folder,
            output_path=output_path,
            pairs=pairs,
            add_footer=not args.no_footer,
            anonymized_suffix=args.suffix,
        )
        return 0
    except Exception as exc:
        print("\n[ERROR] The program terminated with an exception:")
        print(str(exc))
        if os.environ.get("FOLDER_TO_PDF_DEBUG") == "1":
            traceback.print_exc()
        return 1
    finally:
        if should_pause_on_exit(args):
            input("\nPress Enter to close.")


if __name__ == "__main__":
    raise SystemExit(main())
