ReadMe – Folder to Merged PDF Tool
1. Overview

This application processes a folder of documents and produces a single merged PDF.
It performs:

Recursive folder scan (including subfolders)

Document conversion

PDF (.pdf) used directly

Word (.doc, .docx) converted to PDF

PowerPoint (.ppt, .pptx) converted to PDF

PDF merging into a single consolidated file

Per-page footer showing the original relative file path

Optional anonymisation

Replace specified words (e.g. company names) with aliases/codenames

Applied to the final merged PDF

Produces an additional file with _anon suffix

This output can be safely shared or used for AI analysis without revealing sensitive names.

2. Requirements
Mandatory

Windows 10 or later

LibreOffice installed
Download: https://www.libreoffice.org/

The tool uses LibreOffice’s soffice.exe to convert Word/PowerPoint files to PDF.

soffice access

One of the following must be true:

LibreOffice added automatically to the system PATH (default installer setting), or

You set an environment variable:

LIBREOFFICE_PATH = C:\Program Files\LibreOffice\program\soffice.exe

No Python needed

All dependencies are bundled inside the .exe.

3. Installation

Install LibreOffice.

Place the following files in any folder:

folder_to_merged_pdf.exe

readme.txt (this file)

If needed, define the LIBREOFFICE_PATH environment variable:

Press Windows key → “Edit the system environment variables”

Environment Variables → New (under User variables)

Name: LIBREOFFICE_PATH
Value: full path to soffice.exe

Close and reopen File Explorer for the variable to take effect.

4. How to Use
Step 1 – Run the application

Double-click folder_to_merged_pdf.exe
A console window opens.

Step 2 – Enter the root folder

Example:

C:\Users\John\Documents\Data Room


This folder will be scanned recursively.

Step 3 – Choose output path

Press Enter to accept the default (merged PDF inside the selected folder), or

Enter a custom full path ending with .pdf.

Step 4 – Optional anonymisation

The tool asks:

Do you want to anonymise words? [y/N]


If yes:

Enter any number of replacements in the form:

original -> replacement


Example:

eleQtron -> Project Ion
CompanyName -> Target Alpha


Press Enter on an empty line to finish.

Step 5 – Processing

The application will:

Convert supported documents to PDF

Add footers

Merge everything

Apply anonymisation (if requested)

Step 6 – Output files

You will get:

merged_documents.pdf (or your chosen output path)

If anonymisation was enabled:
merged_documents_anon.pdf

The console prints the exact final file path.

5. Supported File Types

Included in scan:

.pdf

.doc, .docx

.ppt, .pptx

Ignored:

.xls, .xlsx

Images

Zip / archives

Any unsupported formats

Only real text in PDFs is anonymised; text inside images or scans cannot be replaced.

6. Common Issues
1. “LibreOffice ‘soffice’ executable not found”

Fix:

Install LibreOffice

Or set LIBREOFFICE_PATH to the full soffice.exe path

2. Some PDFs are skipped

Reason:

Broken or non-standard PDF structures
Fix:

The tool skips problematic pages/files and continues merging

You can manually re-save a problematic PDF via Adobe Reader or an online converter if needed

3. Anonymisation did not replace a word

Causes:

Case-sensitive matching (e.g. “Company” ≠ “company”)

The text is part of an image or scanned page
Fix:

Add multiple variants (e.g. “EleQtron”, “eleQtron”)

Convert scans to OCR PDFs first if needed

7. Notes

The merge order is alphabetical by folder path and filename.

Footers always use relative paths (no drive letters or absolute paths).

Anonymisation outputs a separate PDF; the original merged version is preserved.

8. Support

If something does not work as expected:

Note the error messages printed in the console.

Check that LibreOffice works.

Verify that your folder contains supported documents.

You can share logs or screenshots with the developer if troubleshooting is required.