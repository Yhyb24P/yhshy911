"""Deterministic SVG inspection."""
from pathlib import Path
from lxml import etree


def inspect(path: Path) -> dict:
    try: root = etree.parse(str(path)).getroot()
    except (OSError, etree.XMLSyntaxError) as error: return {"ok": False, "error": str(error)}
    texts = root.xpath("//*[local-name()='text']")
    images = root.xpath("//*[local-name()='image']")
    raw = etree.tostring(root).decode("utf-8", "ignore").lower()
    external = any(str(key).endswith("href") and str(value).startswith(("http://", "https://")) for element in root.iter() for key, value in element.attrib.items())
    return {"ok": True, "text_count": len(texts), "image_count": len(images), "has_nan": "nan" in raw or "inf" in raw, "external": external, "width": root.get("width"), "height": root.get("height"), "viewbox": root.get("viewBox")}
