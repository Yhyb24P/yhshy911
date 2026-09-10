"""Matplotlib panel renderer. It only draws values explicitly present in input."""
from typing import Any
import numpy as np
import pandas as pd
from shared.exceptions import ValidationError


def _series(ax: Any, data: pd.DataFrame, panel: dict[str, Any], kind: str) -> None:
    x, y = panel["x"], panel["y"]
    groups = [(None, data)] if "group" not in panel else list(data.groupby(panel["group"], sort=False))
    for index, (name, frame) in enumerate(groups):
        label = None if name is None else str(name)
        marker = ["o", "s", "^", "D", "v"][index % 5]
        if kind == "line": ax.plot(frame[x], frame[y], marker=marker, ms=3, lw=1, label=label)
        elif kind == "scatter": ax.scatter(frame[x], frame[y], marker=marker, s=16, label=label)
        else: ax.bar(frame[x], frame[y], label=label, hatch=["/", "\\", "x", "-"][index % 4], alpha=0.85)
        uncertainty = panel.get("uncertainty")
        if uncertainty:
            if uncertainty["type"] != "explicit" or "value" not in uncertainty:
                raise ValidationError("Only explicit uncertainty values are renderable; no statistics are inferred")
            column = uncertainty["value"]
            if column not in frame:
                raise ValidationError(f"Missing explicit uncertainty column: {column}")
            ax.errorbar(frame[x], frame[y], yerr=frame[column], fmt="none", color="black", capsize=2)
    if len(groups) > 1: ax.legend(frameon=False, fontsize=6)


def render_panel(ax: Any, data: pd.DataFrame, panel_spec: dict[str, Any], context: dict[str, Any]) -> None:
    kind = panel_spec["type"]
    x, y = panel_spec["x"], panel_spec["y"]
    required = {x, y} | ({panel_spec["group"]} if "group" in panel_spec else set())
    missing = required - set(data.columns)
    if missing: raise ValidationError(f"Missing referenced columns: {sorted(missing)}")
    if kind in {"line", "scatter", "bar"}: _series(ax, data, panel_spec, kind)
    elif kind in {"box", "violin"}:
        groups = list(data.groupby(x, sort=False)); values = [f[y].dropna().to_numpy() for _, f in groups]
        (ax.boxplot if kind == "box" else ax.violinplot)(values)
        ax.set_xticks(range(1, len(groups)+1), [str(n) for n, _ in groups])
    elif kind == "heatmap": ax.imshow(data.pivot_table(index=y, columns=x, aggfunc="size", fill_value=0), aspect="auto", cmap="viridis")
    elif kind == "confusion_matrix": ax.imshow(data.pivot_table(index=y, columns=x, aggfunc="size", fill_value=0), cmap="Blues")
    elif kind == "volcano": ax.scatter(data[x], data[y], s=14)
    elif kind in {"roc", "pr", "calibration"}: ax.plot(data[x], data[y], marker="o", ms=3, lw=1)
    else: raise ValidationError(f"Unsupported plot type: {kind}")
    ax.set_xlabel(panel_spec["x_label"]); ax.set_ylabel(panel_spec["y_label"]); ax.grid(False)
