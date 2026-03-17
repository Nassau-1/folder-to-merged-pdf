# Folder To Merged PDF

Small Windows-first utility that:

- scans a folder recursively
- converts supported Office files to PDF with LibreOffice
- merges the PDFs into one file
- adds a footer showing the original relative file path
- optionally anonymizes terms in the merged PDF

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

## Build Artifact Hygiene

`build/` and `dist/` are generated outputs and are intentionally excluded from git.

If you want to ship a Windows executable, keep using the existing `folder_to_merged_pdf.spec` file and build it separately from the source repo.
