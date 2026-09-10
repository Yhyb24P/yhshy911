"""Deterministic left-to-right layout without inferred semantics."""
from typing import Any


def positions(nodes: list[dict[str, Any]]) -> dict[str, tuple[int, int]]:
    return {node["id"]: (70 + 180 * (i % 4), 70 + 120 * (i // 4)) for i, node in enumerate(nodes)}
