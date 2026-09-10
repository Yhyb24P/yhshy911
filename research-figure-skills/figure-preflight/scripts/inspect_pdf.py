"""PDF geometry, text and font inspection using PyMuPDF."""
from pathlib import Path
import fitz


def inspect(path: Path) -> dict:
    doc = fitz.open(path)
    if not doc.page_count: return {"ok": False, "error": "empty PDF"}
    page = doc[0]; rect = page.rect; spans = [span for block in page.get_text("dict")["blocks"] if "lines" in block for line in block["lines"] for span in line["spans"]]
    fonts = doc.get_page_fonts(0, full=True)
    return {"ok": True, "pages": doc.page_count, "width_mm": rect.width * 25.4 / 72, "height_mm": rect.height * 25.4 / 72, "min_font_pt": min((s["size"] for s in spans), default=None), "text": page.get_text(), "fonts": [f[3] for f in fonts], "embedded_fonts": bool(fonts)}
