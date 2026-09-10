#!/usr/bin/env python3
"""Audit outputs only; it never alters visual files or scientific content."""
import argparse, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(Path(__file__).parent))
from shared.config import load_profile
from shared.io import read_yaml
from inspect_pdf import inspect as inspect_pdf
from inspect_raster import inspect as inspect_raster
from inspect_svg import inspect as inspect_svg
from inspect_panels import inspect as inspect_panels
from report import final_status


def run(path: Path, spec_path: Path | None = None, profile_name: str = "nature") -> Path:
    path = path.resolve(); profile = load_profile(ROOT, profile_name); output = path.parent
    spec = read_yaml(spec_path) if spec_path else None; lines = []
    if path.suffix.lower() == ".pdf":
        info = inspect_pdf(path); lines += [f"{'PASS' if info.get('ok') else 'FAIL'}  PDF parseable", f"PASS  Width: {info.get('width_mm', 0):.1f} mm", f"PASS  Height: {info.get('height_mm', 0):.1f} mm"]
        minimum = info.get("min_font_pt"); lines.append(("PASS" if minimum and minimum >= profile["typography"]["min_font_pt"] else "FAIL") + f"  Minimum detected font: {minimum} pt")
        lines.append(("PASS" if info.get("embedded_fonts") else "WARN") + "  Embedded fonts detected" if info.get("embedded_fonts") else "WARN  No embedded fonts detected")
        text = info.get("text", "")
    else: text = ""
    svg = output / "figure.svg"
    if svg.exists():
        si = inspect_svg(svg); lines += [("PASS" if si["ok"] else "FAIL") + "  SVG XML parseable", ("PASS" if si.get("text_count", 0) else "FAIL") + f"  SVG editable text elements: {si.get('text_count', 0)}", ("FAIL" if si.get("has_nan") else "PASS") + "  SVG has no NaN/inf coordinates", ("FAIL" if si.get("external") else "PASS") + "  SVG has no external resources"]
        text += " ".join(node.text or "" for node in __import__("lxml").etree.parse(str(svg)).xpath("//*[local-name()='text']"))
    png = output / "figure.png"
    if png.exists():
        ri = inspect_raster(png, (inspect_pdf(path).get("width_mm") if path.suffix.lower()==".pdf" else None)); good = ri["effective_dpi"] >= profile["export"]["raster"]["dpi"]
        lines.append(("PASS" if good else "FAIL") + f"  Effective raster DPI: {ri['effective_dpi']:.0f}")
        lines.append(("PASS" if ri["mode"] in {"RGB", "RGBA"} else "WARN") + f"  Raster mode: {ri['mode']}")
    if spec:
        labels = [p["id"] for p in spec["figure"]["panels"]]; lines.append(("PASS" if inspect_panels(text, labels) else "FAIL") + "  Panel labels: " + ", ".join(labels))
        for panel in spec["figure"]["panels"]:
            lines.append(("PASS" if panel.get("x_label") and panel.get("y_label") else "FAIL") + f"  Axis labels present for panel {panel['id']}")
        if any("statistics" in p for p in spec["figure"]["panels"]): lines.append("MANUAL_CHECK  Statistical interpretation requires scientific review.")
    lines.append(("PASS" if (output / "figure_provenance.yaml").is_file() else "FAIL") + "  Provenance exists")
    lines.append("MANUAL_CHECK  Scientific, causal and biological validity cannot be established by visual QA.")
    report = output / "figure-preflight-report.md"; report.write_text("# Figure Preflight Report\n\n## Input\n\nFile: " + str(path) + "\nProfile: " + profile_name + "\n\n## Checks\n\n" + "\n\n".join(lines) + "\n\n## Final\n\nSTATUS: " + final_status(lines) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("figure", type=Path); parser.add_argument("--spec", type=Path); parser.add_argument("--profile", default="nature")
    args = parser.parse_args()
    print(run(args.figure, args.spec, args.profile))
