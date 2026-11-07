import io
import math
import os
import logging
import re
from typing import Callable, Optional, List, Dict, Set
import pymupdf as fitz
from fontTools.ttLib import TTFont
from pypdf import PdfReader
from app.core.limits import MAX_OCR_PIXELS
from app.services.document_processor import DocumentRejected
logger = logging.getLogger(__name__)
TOUNICODE_SECTION_PATTERN = re.compile(rb"begin(bfchar|bfrange)(.*?)end\1", re.S)
TOUNICODE_TOKEN_PATTERN = re.compile(rb"<([0-9A-Fa-f]+)>|\[[^\]]*\]")
OBJECT_REFERENCE_PATTERN = re.compile(r"(\d+) 0 R")
REPLACEMENT_CHARACTER = 0xFFFD
PageOcr = Callable[[bytes], str]
class PDFService:
    OCR_RENDER_DPI = 150
    @staticmethod
    def _is_cjk_char(c: str) -> bool:
        if not c:
            return False
        cp = ord(c)
        return (
            0x4E00 <= cp <= 0x9FFF
            or 0x3400 <= cp <= 0x4DBF
            or 0x20000 <= cp <= 0x2A6DF
            or 0x2A700 <= cp <= 0x2B73F
            or 0xFF00 <= cp <= 0xFFEF
            or 0x3000 <= cp <= 0x303F
            or 0xFE30 <= cp <= 0xFE4F
            or 0x3100 <= cp <= 0x312F
            or 0x31A0 <= cp <= 0x31BF
        )
    @staticmethod
    def _is_valid_char(c: str) -> bool:
        return (
            PDFService._is_cjk_char(c)
            or "\u0020" <= c <= "\u007e"
            or c in "\n\r\t"
            or "\u2010" <= c <= "\u2e7f"
            or "\u2460" <= c <= "\u24ff"
        )
    @staticmethod
    def _is_garbled(text: str, threshold: float = 0.35) -> bool:
        if not text or len(text.strip()) < 10:
            return True
        cjk_count = sum(1 for c in text if PDFService._is_cjk_char(c))
        if cjk_count > 5:
            return False
        valid_count = sum(1 for c in text if PDFService._is_valid_char(c))
        valid_ratio = valid_count / len(text)
        return valid_ratio < (1 - threshold)
    @staticmethod
    def _alternate_glyph_unicodes(font_bytes: bytes) -> Dict[int, int]:
        font = TTFont(io.BytesIO(font_bytes))
        if "GSUB" not in font or font["GSUB"].table.LookupList is None:
            return {}
        unicode_of_glyph: Dict[str, int] = {}
        for code_point, glyph_name in sorted((font.getBestCmap() or {}).items()):
            unicode_of_glyph.setdefault(glyph_name, code_point)
        glyph_ids = {name: gid for gid, name in enumerate(font.getGlyphOrder())}
        alternates: Dict[int, int] = {}
        for lookup in font["GSUB"].table.LookupList.Lookup:
            for subtable in lookup.SubTable:
                mapping = getattr(getattr(subtable, "ExtSubTable", subtable), "mapping", None) or {}
                for source, target in mapping.items():
                    if target not in unicode_of_glyph and source in unicode_of_glyph:
                        alternates.setdefault(glyph_ids[target], unicode_of_glyph[source])
        return alternates
    @staticmethod
    def _mapped_codes(cmap_stream: bytes) -> Set[int]:
        codes: Set[int] = set()
        for kind, body in TOUNICODE_SECTION_PATTERN.findall(cmap_stream):
            tokens = [int(m.group(1), 16) if m.group(1) else None for m in TOUNICODE_TOKEN_PATTERN.finditer(body)]
            if kind == b"bfchar":
                codes.update(code for code, target in zip(tokens[0::2], tokens[1::2]) if target != REPLACEMENT_CHARACTER)
            else:
                for start, end, target in zip(tokens[0::3], tokens[1::3], tokens[2::3]):
                    if target != REPLACEMENT_CHARACTER:
                        codes.update(range(start, end + 1))
        return codes
    @classmethod
    def _map_unmapped_alternate_glyphs(cls, doc) -> int:
        added = 0
        seen = set()
        for page in doc:
            for xref, _, font_type, name, _, encoding, *_ in page.get_fonts(full=True):
                if xref in seen or font_type != "Type0" or not encoding.startswith("Identity"):
                    continue
                seen.add(xref)
                try:
                    kind, to_unicode = doc.xref_get_key(xref, "ToUnicode")
                    if kind != "xref":
                        continue
                    kind, descendants = doc.xref_get_key(xref, "DescendantFonts")
                    if kind == "xref":
                        descendants = doc.xref_object(int(descendants.split()[0]))
                    descendant = int(OBJECT_REFERENCE_PATTERN.search(descendants).group(1))
                    if (
                        doc.xref_get_key(descendant, "Subtype")[1] != "/CIDFontType2"
                        or doc.xref_get_key(descendant, "CIDToGIDMap")[1] not in ("null", "/Identity")
                    ):
                        continue
                    descriptor = int(doc.xref_get_key(descendant, "FontDescriptor")[1].split()[0])
                    font_file = int(doc.xref_get_key(descriptor, "FontFile2")[1].split()[0])
                    alternates = cls._alternate_glyph_unicodes(doc.xref_stream(font_file))
                    stream_xref = int(to_unicode.split()[0])
                    cmap_stream = doc.xref_stream(stream_xref)
                    mapped = cls._mapped_codes(cmap_stream)
                    missing = {gid: code_point for gid, code_point in alternates.items() if gid not in mapped}
                    end = cmap_stream.rfind(b"endcmap")
                    if not missing or end < 0:
                        continue
                    entries = "\n".join(
                        f"<{gid:04X}> <{chr(code_point).encode('utf-16-be').hex().upper()}>"
                        for gid, code_point in sorted(missing.items())
                    )
                    section = f"\n{len(missing)} beginbfchar\n{entries}\nendbfchar\n".encode("ascii")
                    doc.update_stream(stream_xref, cmap_stream[:end] + section + cmap_stream[end:])
                    added += len(missing)
                except Exception as e:
                    logger.debug(f"字型 {name} (xref={xref}) 的替代字形對應檢查失敗: {e}")
        return added
    @classmethod
    def _render_page_png(cls, page) -> bytes:
        zoom = cls.OCR_RENDER_DPI / 72.0
        width = max(page.rect.width, 1.0) * zoom
        height = max(page.rect.height, 1.0) * zoom
        if width * height > MAX_OCR_PIXELS:
            zoom *= math.sqrt(MAX_OCR_PIXELS / (width * height))
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return pix.tobytes("png")
    @classmethod
    def _ocr_page_sync(cls, ocr: PageOcr, img_bytes: bytes, page_num: int) -> str:
        try:
            content = ocr(img_bytes).strip()
            if content:
                logger.info(f"第 {page_num} 頁 Vision OCR 辨識成功 ({len(content)} 字)")
                return content
            logger.warning(f"第 {page_num} 頁 Vision OCR 沒有回傳文字")
        except Exception as e:
            logger.warning(f"第 {page_num} 頁執行 Vision OCR 失敗: {type(e).__name__}: {e}")
        return f"[第 {page_num} 頁為掃描圖片或複雜版面，已記錄]"
    @classmethod
    def extract_text_robust(cls, file_path: str, max_ocr_pages: Optional[int], ocr: Optional[PageOcr]) -> str:
        return cls._extract_sync_internal(file_path, max_ocr_pages, ocr)
    @classmethod
    def _extract_sync_internal(cls, file_path: str, max_ocr_pages: Optional[int], ocr: Optional[PageOcr]) -> str:
        import concurrent.futures
        try:
            doc = fitz.open(file_path)
            if doc.is_encrypted and not doc.authenticate(""):
                doc.close()
                raise DocumentRejected("PDF 文件被密碼保護，無法讀取")
            mapped_glyphs = cls._map_unmapped_alternate_glyphs(doc)
            if mapped_glyphs > 0:
                logger.info(f"PDF 檔案 {os.path.basename(file_path)} 補上了 {mapped_glyphs} 個替代字形的 ToUnicode 對應")
            pages_text: List[Optional[str]] = [None] * len(doc)
            text_pages = 0
            ocr_jobs = []
            for page_idx in range(len(doc)):
                page_num = page_idx + 1
                page = doc[page_idx]
                page_raw = page.get_text("text")
                if page_raw and page_raw.strip() and not cls._is_garbled(page_raw):
                    pages_text[page_idx] = f"--- 第 {page_num} 頁 ---\n{page_raw.strip()}\n"
                    text_pages += 1
                else:
                    blocks = page.get_text("blocks")
                    block_texts = [b[4].strip() for b in blocks if len(b) >= 5 and b[4].strip()]
                    joined_blocks = "\n".join(block_texts)
                    
                    if joined_blocks and not cls._is_garbled(joined_blocks):
                        pages_text[page_idx] = f"--- 第 {page_num} 頁 ---\n{joined_blocks}\n"
                        text_pages += 1
                    else:
                        logger.warning(f"第 {page_num} 頁文字為空或判定為亂碼 (文字長度: {len(page_raw)})，加入 OCR 佇列")
                        ocr_jobs.append((page_idx, page_num, page))
            if ocr_jobs and max_ocr_pages is not None and len(ocr_jobs) > max_ocr_pages:
                logger.warning(f"需要 OCR 的頁數 ({len(ocr_jobs)}) 超過上限 {max_ocr_pages}，其餘頁面略過")
                for page_idx, page_num, _ in ocr_jobs[max_ocr_pages:]:
                    pages_text[page_idx] = f"--- 第 {page_num} 頁 ---\n[本頁未進行 OCR：超過每份文件的 OCR 頁數上限]\n"
                ocr_jobs = ocr_jobs[:max_ocr_pages]
            if ocr_jobs and ocr is not None:
                logger.info(f"正在對 {len(ocr_jobs)} 頁純圖檔/掃描頁面啟動 Vision OCR 並行辨識...")
                rendered_jobs = []
                for page_idx, page_num, page in ocr_jobs:
                    try:
                        rendered_jobs.append((page_idx, page_num, cls._render_page_png(page)))
                    except Exception as e:
                        logger.warning(f"第 {page_num} 頁點陣化失敗: {e}")
                        pages_text[page_idx] = f"--- 第 {page_num} 頁 ---\n[本頁為圖檔或無可提取純文字]\n"
                max_workers = max(1, min(len(rendered_jobs), 4))
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_job = {
                        executor.submit(cls._ocr_page_sync, ocr, job[2], job[1]): job
                        for job in rendered_jobs
                    }
                    for future in concurrent.futures.as_completed(future_to_job):
                        job = future_to_job[future]
                        page_idx = job[0]
                        page_num = job[1]
                        try:
                            ocr_text = future.result()
                            if ocr_text and not ocr_text.startswith("[第 "):
                                pages_text[page_idx] = f"--- 第 {page_num} 頁 (OCR 辨識) ---\n{ocr_text.strip()}\n"
                                text_pages += 1
                            else:
                                pages_text[page_idx] = f"--- 第 {page_num} 頁 ---\n{ocr_text.strip()}\n"
                        except Exception as e:
                            logger.warning(f"第 {page_num} 頁 OCR 任務執行失敗: {e}")
                            pages_text[page_idx] = f"--- 第 {page_num} 頁 ---\n[本頁為圖檔或無可提取純文字]\n"
            elif ocr_jobs:
                for job in ocr_jobs:
                    page_idx = job[0]
                    page_num = job[1]
                    pages_text[page_idx] = f"--- 第 {page_num} 頁 ---\n[本頁為圖檔或無可提取純文字]\n"
            doc.close()
            if not text_pages:
                raise DocumentRejected("PDF 文件中沒有可擷取的文字：每一頁都是圖片或無法辨識的文字，且 OCR 未設定或辨識失敗")
            final_pages = [p for p in pages_text if p is not None]
            full_text = "\n".join(final_pages).strip()
            logger.info(f"成功從 PDF 擷取 {len(final_pages)} 頁，共 {len(full_text)} 字元")
            return full_text
        except DocumentRejected:
            raise
        except Exception as e:
            logger.warning(f"PyMuPDF 穩健讀取失敗 ({e})，啟動 pypdf 備援降級")
        text_content = []
        with open(file_path, 'rb') as file:
            pdf_reader = PdfReader(file)
            if pdf_reader.is_encrypted:
                try:
                    decrypted = pdf_reader.decrypt("")
                except Exception:
                    decrypted = False
                if not decrypted:
                    raise DocumentRejected("PDF 文件被密碼保護，無法讀取")
            for page_num, page in enumerate(pdf_reader.pages):
                try:
                    page_text = page.extract_text()
                    if page_text and page_text.strip():
                        text_content.append(f"--- 第 {page_num + 1} 頁 ---\n{page_text.strip()}\n")
                except Exception:
                    continue
        if not text_content:
            raise DocumentRejected("PDF 文件中沒有可擷取的文字內容（可能是純圖檔掃描件）")
        return "\n".join(text_content)