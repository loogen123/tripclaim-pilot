from __future__ import annotations

import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from pypdf import PdfReader

try:
    from docx import Document as DocxDocument
except Exception:
    DocxDocument = None


SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".ofd",
    ".docx",
    ".doc",
    ".txt",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
}
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

_PADDLE_OCR_ENGINE: Any = None
_PADDLE_OCR_READY: bool | None = None
_RAPID_OCR_ENGINE: Any = None
_RAPID_OCR_READY: bool | None = None


def _get_paddle_ocr_engine() -> Any:
    global _PADDLE_OCR_ENGINE, _PADDLE_OCR_READY
    if _PADDLE_OCR_READY is False:
        return None
    if _PADDLE_OCR_ENGINE is not None:
        return _PADDLE_OCR_ENGINE
    try:
        from paddleocr import PaddleOCR  # type: ignore

        _PADDLE_OCR_ENGINE = PaddleOCR(use_angle_cls=True, lang="ch")
        _PADDLE_OCR_READY = True
        return _PADDLE_OCR_ENGINE
    except Exception:
        _PADDLE_OCR_READY = False
        return None


def _get_rapid_ocr_engine() -> Any:
    global _RAPID_OCR_ENGINE, _RAPID_OCR_READY
    if _RAPID_OCR_READY is False:
        return None
    if _RAPID_OCR_ENGINE is not None:
        return _RAPID_OCR_ENGINE
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore

        _RAPID_OCR_ENGINE = RapidOCR()
        _RAPID_OCR_READY = True
        return _RAPID_OCR_ENGINE
    except Exception:
        _RAPID_OCR_READY = False
        return None


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
    if ext == ".ofd":
        return extract_ofd_text(path)
    if ext in {".docx", ".doc"}:
        return extract_docx_text(path)
    if ext == ".txt":
        return path.read_text(encoding="utf-8", errors="ignore")
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
        return extract_image_text(path)
    return ""


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    text = "\n".join(parts)
    
    # 智能降级 OCR：文本过少或关键锚点缺失时触发 PDF 页转图 OCR
    clean_len = len(text.replace(" ", "").replace("\n", "").strip())
    anchors = ["预约报销", "项目编号", "支付方式", "交通", "发票", "行程单"]
    needs_ocr = clean_len < 100 or not any(anchor in text for anchor in anchors)
    if needs_ocr:
        ocr_text = extract_pdf_text_by_ocr(path)
        if len("".join(ocr_text.split())) > len("".join(text.split())):
            return ocr_text
    return text


def extract_docx_text(path: Path) -> str:
    if DocxDocument is None:
        return ""
    try:
        doc = DocxDocument(str(path))
        parts: list[str] = [p.text for p in doc.paragraphs if p.text]

        # 兼容“docx里只有图片”的场景：提取内嵌图片并做OCR
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            try:
                with zipfile.ZipFile(path, "r") as zf:
                    for name in zf.namelist():
                        lowered = name.lower()
                        if not lowered.startswith("word/media/"):
                            continue
                        if not lowered.endswith((".png", ".jpg", ".jpeg", ".bmp", ".webp")):
                            continue
                        raw = zf.read(name)
                        img_path = temp_dir_path / Path(name).name
                        img_path.write_bytes(raw)
                        img_text = extract_image_text(img_path)
                        if img_text.strip():
                            parts.append(img_text)
            except Exception:
                pass

        return "\n".join(parts)
    except Exception:
        return ""


def extract_ofd_text(path: Path) -> str:
    try:
        if not zipfile.is_zipfile(path):
            return ""
        parts: list[str] = []
        with zipfile.ZipFile(path, "r") as zf:
            for name in zf.namelist():
                lowered = name.lower()
                if not lowered.endswith(".xml"):
                    continue
                if "sign" in lowered or "seal" in lowered:
                    continue
                raw = zf.read(name)
                text = raw.decode("utf-8", errors="ignore")
                if not text.strip():
                    text = raw.decode("gb18030", errors="ignore")
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"\s+", " ", text).strip()
                if text:
                    parts.append(text)
        return "\n".join(parts)
    except Exception:
        return ""


def extract_pdf_text_by_ocr(path: Path) -> str:
    ocr_parts: list[str] = []
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        image_paths: list[Path] = []
        try:
            from pdf2image import convert_from_path

            images = convert_from_path(str(path), dpi=220)
            for i, img in enumerate(images):
                temp_img_path = temp_dir_path / f"page_{i}.jpg"
                img.save(temp_img_path, "JPEG")
                image_paths.append(temp_img_path)
        except Exception:
            try:
                import fitz  # type: ignore

                doc = fitz.open(str(path))
                for i, page in enumerate(doc):
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    temp_img_path = temp_dir_path / f"page_{i}.jpg"
                    pix.save(str(temp_img_path))
                    image_paths.append(temp_img_path)
            except Exception:
                return ""

        for img_path in image_paths:
            ocr_parts.append(extract_image_text(img_path))
    return "\n".join(ocr_parts)


def extract_image_text(path: Path) -> str:
    def _rapidocr_fallback(image_path: Path) -> str:
        try:
            engine = _get_rapid_ocr_engine()
            if engine is None:
                return ""
            out, _ = engine(str(image_path))
            if out:
                return "\n".join(item[1] for item in out if len(item) > 1 and item[1])
        except Exception:
            pass
        return ""

    try:
        from PIL import Image, ImageEnhance, ImageOps
        ocr = _get_paddle_ocr_engine()
        if ocr is None:
            return _rapidocr_fallback(path)

        def _extract_from_result(result: object) -> str:
            if not result:
                return ""
            lines: list[str] = []
            for row in result[0]:
                text = row[1][0] if row and row[1] else ""
                if text:
                    lines.append(text)
            return "\n".join(lines)

        result = ocr.ocr(str(path), cls=True)
        text = _extract_from_result(result)
        if len("".join(text.split())) >= 8:
            return text

        # 微信截图等小字场景：增强+放大后二次识别
        with Image.open(path) as img:
            gray = ImageOps.grayscale(img)
            contrast = ImageEnhance.Contrast(gray).enhance(1.8)
            sharp = ImageEnhance.Sharpness(contrast).enhance(2.0)
            upscaled = sharp.resize((sharp.width * 2, sharp.height * 2))
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            upscaled.save(tmp_path, format="JPEG", quality=95)

        try:
            result2 = ocr.ocr(str(tmp_path), cls=True)
            text2 = _extract_from_result(result2)
            better = text2 if len("".join(text2.split())) > len("".join(text.split())) else text
            if len("".join(better.split())) >= 8:
                return better
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

        text3 = _rapidocr_fallback(path)
        if len("".join(text3.split())) > len("".join(text.split())):
            return text3
        return text
    except Exception:
        return _rapidocr_fallback(path)
