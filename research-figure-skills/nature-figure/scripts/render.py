#!/usr/bin/env python3
"""Render a validated, evidence-backed figure at final physical dimensions."""
import argparse, logging, shutil, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shared.config import figure_size_inches, load_profile
from shared.io import read_table, read_yaml
from shared.provenance import write_provenance
from shared.validation import validate_figure_spec
from renderers import render_panel


def run(spec_path: Path) -> Path:
    spec_path = spec_path.resolve(); spec = read_yaml(spec_path)
    validate_figure_spec(spec, ROOT / "schemas" / "figure_spec.schema.json")
    figure = spec["figure"]; profile = load_profile(ROOT, figure["journal_profile"])
    source = (spec_path.parent / figure["source"]["path"]).resolve()
    data = read_table(source, figure["source"]["type"])
    output = (spec_path.parent / figure["output"]["directory"]).resolve(); output.mkdir(parents=True, exist_ok=True)
    typ = profile["typography"]; plt.rcParams.update({"font.size": typ["normal_font_pt"], "font.family": "DejaVu Sans", "pdf.fonttype": profile["matplotlib"]["pdf_fonttype"], "ps.fonttype": profile["matplotlib"]["ps_fonttype"], "svg.fonttype": "none", "axes.grid": False})
    width, height = figure_size_inches(profile, figure["dimensions"], len(figure["panels"]))
    n = len(figure["panels"]); fig, axes = plt.subplots(1, n, figsize=(width, height), squeeze=False); axes = axes.ravel()
    for ax, panel in zip(axes, figure["panels"]):
        render_panel(ax, data, panel, {"profile": profile})
        ax.text(-0.13, 1.05, panel["id"], transform=ax.transAxes, fontsize=typ["panel_label_pt"], fontweight=typ["panel_label_weight"], va="top")
    fig.tight_layout()
    for fmt in figure["output"]["formats"]:
        kwargs = {"format": fmt, "bbox_inches": "tight"}
        if fmt == "png": kwargs["dpi"] = profile["export"]["raster"]["dpi"]
        fig.savefig(output / f"figure.{fmt}", **kwargs)
    plt.close(fig)
    shutil.copy2(spec_path, output / "figure_spec.yaml")
    write_provenance(output / "figure_provenance.yaml", figure["id"], source, spec_path, "nature-figure/scripts/render.py", ROOT)
    from importlib.util import spec_from_file_location, module_from_spec
    target = ROOT / "figure-preflight" / "scripts" / "preflight.py"; module_spec = spec_from_file_location("preflight", target); module = module_from_spec(module_spec); module_spec.loader.exec_module(module)
    module.run(output / "figure.pdf", output / "figure_spec.yaml", figure["journal_profile"])
    return output


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(); parser.add_argument("--spec", required=True, type=Path)
    try: print(run(parser.parse_args().spec))
    except Exception as error: logging.error("FAIL_CLOSED: %s", error); raise SystemExit(2)
