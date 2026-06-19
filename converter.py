import csv
import mimetypes
import os
import subprocess
from pathlib import Path

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import fitz  # PyMuPDF
import pdfplumber
from docx import Document


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


def epub_to_text(path: str) -> str:
    book = epub.read_epub(path, options={"ignore_ncx": True})
    parts = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        if text:
            parts.append(text)
    return "\n".join(parts)


def docx_to_text(path: str) -> str:
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def csv_to_text(path: str) -> str:
    lines = []
    with open(path, newline="", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f)
        for row in reader:
            lines.append(" | ".join(cell.strip() for cell in row))
    return "\n".join(lines)


def detect_type(path: str) -> str:
    ext = Path(path).suffix.lower()
    mapping = {
        ".pdf":  "pdf",
        ".epub": "epub",
        ".mobi": "epub",
        ".azw3": "epub",
        ".docx": "docx",
        ".csv":  "csv",
        ".txt":  "txt",
    }
    if ext in mapping:
        return mapping[ext]
    mime, _ = mimetypes.guess_type(path)
    return mime or "unknown"


def convert(path: str, use_ocr: bool = False) -> str:
    kind = detect_type(path)
    if kind == "pdf":
        if use_ocr and is_likely_scanned_pdf(path):
            return pdf_to_text_with_ocr(path)
        return pdf_to_text(path)
    elif kind == "epub":
        return epub_to_text(path)
    elif kind == "docx":
        return docx_to_text(path)
    elif kind == "csv":
        return csv_to_text(path)
    elif kind == "txt":
        return Path(path).read_text(encoding="utf-8", errors="ignore")
    else:
        raise ValueError(f"Unsupported file type: {Path(path).suffix}")
