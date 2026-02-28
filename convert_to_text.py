#!/usr/bin/env python3
import argparse
import mimetypes
import os
import subprocess
import sys
from pathlib import Path

import fitz  # PyMuPDF
import pdfplumber
from docx import Document

def is_likely_scanned_pdf(path):
    # Simple heuristic: if pdfplumber sees almost no text on first pages
    with pdfplumber.open(path) as pdf:
        pages = pdf.pages[:3]
        text = "".join((p.extract_text() or "") for p in pages)
        return len(text.strip()) < 50

def pdf_to_text(path):
    doc = fitz.open(path)
    return "\n".join(page.get_text() for page in doc)

def pdf_to_text_with_ocr(path):
    tmp = Path(path).with_suffix(".ocr.pdf")
    subprocess.run(
        ["ocrmypdf", "--skip-text", path, str(tmp)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        return pdf_to_text(str(tmp))
    finally:
        if tmp.exists():
            tmp.unlink()

def epub_to_text_with_calibre(path):
    out = Path(path).with_suffix(".txt")
    subprocess.run(
        ["ebook-convert", path, str(out)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    text = out.read_text(encoding="utf-8", errors="ignore")
    out.unlink(missing_ok=True)
    return text

def docx_to_text(path):
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs)

def csv_to_text(path):
    import csv
    lines = []
    with open(path, newline="", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f)
        for row in reader:
            lines.append(" | ".join(cell.strip() for cell in row))
    return "\n".join(lines)

def detect_type(path):
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext in {".epub", ".mobi", ".azw3"}:
        return "epub"
    if ext in {".docx"}:
        return "docx"
    if ext in {".csv"}:
        return "csv"
    # Fallback on MIME if needed
    mime, _ = mimetypes.guess_type(path)
    return mime or "unknown"

def convert(path, use_ocr=False):
    kind = detect_type(path)
    if kind == "pdf":
        if use_ocr and is_likely_scanned_pdf(path):
            return pdf_to_text_with_ocr(path)
        return pdf_to_text(path)
    elif kind == "epub":
        return epub_to_text_with_calibre(path)
    elif kind == "docx":
        return docx_to_text(path)
    elif kind == "csv":
        return csv_to_text(path)
    else:
        raise ValueError(f"Unsupported or unknown file type: {path} ({kind})")

def main():
    parser = argparse.ArgumentParser(description="Convert document to plain text.")
    parser.add_argument("input", help="Input file path")
    parser.add_argument("--ocr-fallback", action="store_true",
                        help="Use OCR for scanned PDFs")
    args = parser.parse_args()

    path = args.input
    if not os.path.isfile(path):
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    try:
        text = convert(path, use_ocr=args.ocr_fallback)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)

    sys.stdout.write(text)

if __name__ == "__main__":
    main()
