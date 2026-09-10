"""Raster dimensions and genuine effective DPI inspection."""
from pathlib import Path
from PIL import Image


def inspect(path: Path, width_mm: float | None = None) -> dict:
    with Image.open(path) as image:
        dpi = image.info.get("dpi", (0, 0)); effective = image.width / (width_mm / 25.4) if width_mm else min(dpi)
        return {"width_px": image.width, "height_px": image.height, "dpi": dpi, "effective_dpi": effective, "mode": image.mode, "alpha": "A" in image.mode}
