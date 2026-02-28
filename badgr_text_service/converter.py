import mimetypes
import os
import subprocess
from pathlib import Path

import fitz  # PyMuPDF
import pdfplumber
from docx import Document
import csv

def is_likely_scanned_pdf(path: str) -> bool:
    with pdfplumber.open(path) as pdf:
        pages = pdf.pages[:3]
        text = "".join((p.extract_text() or "") for p in pages)
        return len(text.strip()) < 50

def pdf_to_text(path: str) -> str:
    doc = fitz.open(path)
    return "\n".join(page.get_text() for page in doc)

def pdf_to_text_with_ocr(path: str) -> str:
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

def epub_to_text_with_calibre(path: str) -> str:
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

def docx_to_text(path: str) -> str:
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs)

def csv_to_text(path: str) -> str:
    lines = []
    with open(path, newline="", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f)
        for row in reader:
            lines.append(" | ".join(cell.strip() for cell in row))
    return "\n".join(lines)

def detect_type(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext in {".epub", ".mobi", ".azw3"}:
        return "epub"
    if ext in {".docx"}:
        return "docx"
    if ext in {".csv"}:
        return "csv"
    mime, _ = mimetypes.guess_type(path)
    return mime or "unknown"

def convert(path: str, use_ocr: bool = False) -> str:
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
