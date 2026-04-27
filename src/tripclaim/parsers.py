from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

try:
    from docx import Document as DocxDocument
except Exception:
    DocxDocument = None


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".png", ".jpg", ".jpeg"}
IGNORED_DIR_NAMES = {
    ".git",
    ".trae",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "output",
}


def scan_files(folder: Path) -> list[Path]:
    files: list[Path] = []
    for file_path in folder.rglob("*"):
        if not file_path.is_file():
            continue
        rel_parts = set(file_path.relative_to(folder).parts)
        if any(part in IGNORED_DIR_NAMES for part in rel_parts):
            continue
        if any(part.endswith(".egg-info") for part in rel_parts):
            continue
        if file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(file_path)
    return sorted(files)


def extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return extract_pdf_text(path)
    if ext in {".docx", ".doc"}:
        return extract_docx_text(path)
    if ext == ".txt":
        return path.read_text(encoding="utf-8", errors="ignore")
    if ext in {".png", ".jpg", ".jpeg"}:
        return extract_image_text(path)
    return ""


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def extract_docx_text(path: Path) -> str:
    if DocxDocument is None:
        return ""
    try:
        doc = DocxDocument(str(path))
        return "\n".join(p.text for p in doc.paragraphs if p.text)
    except Exception:
        return ""


def extract_image_text(path: Path) -> str:
    try:
        from paddleocr import PaddleOCR  # type: ignore

        ocr = PaddleOCR(use_angle_cls=True, lang="ch")
        result = ocr.ocr(str(path), cls=True)
        if not result:
            return ""
        lines: list[str] = []
        for row in result[0]:
            text = row[1][0] if row and row[1] else ""
            if text:
                lines.append(text)
        return "\n".join(lines)
    except Exception:
        return ""
