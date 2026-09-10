"""Profile loading and final physical-size calculations."""
from pathlib import Path
from typing import Any
import yaml
from .exceptions import ValidationError

MM_PER_INCH = 25.4


def load_profile(root: Path, name: str) -> dict[str, Any]:
    path = root / "nature-figure" / "config" / f"{name}.yaml"
    if not path.is_file():
        raise ValidationError(f"Unknown journal profile: {name}")
    with path.open(encoding="utf-8") as handle:
        profile = yaml.safe_load(handle)
    if "extends" in profile:
        base = load_profile(root, str(profile.pop("extends")))
        base.update(profile)
        return base
    return profile


def figure_size_inches(profile: dict[str, Any], dimensions: dict[str, Any], panels: int) -> tuple[float, float]:
    if "preset" in dimensions:
        preset = dimensions["preset"]
        key = {"single-column": "single_column_mm", "double-column": "double_column_mm"}.get(preset)
        if key is None:
            raise ValidationError(f"Invalid dimensions preset: {preset}")
        width = float(profile["dimensions"][key])
        height = min(float(profile["dimensions"]["max_height_mm"]), max(55.0, 48.0 * ((panels + 1) // 2)))
    else:
        width, height = float(dimensions["width_mm"]), float(dimensions["height_mm"])
        if height > float(profile["dimensions"]["max_height_mm"]):
            raise ValidationError("Requested height exceeds profile maximum")
    return width / MM_PER_INCH, height / MM_PER_INCH
