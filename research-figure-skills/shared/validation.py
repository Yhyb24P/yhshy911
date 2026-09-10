"""Schema and semantic validation; failures are intentionally closed."""
import json
from pathlib import Path
from typing import Any
from jsonschema import Draft202012Validator
from .exceptions import ValidationError


def validate_schema(value: dict[str, Any], schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda e: list(e.path))
    if errors:
        raise ValidationError("Invalid schema: " + "; ".join(error.message for error in errors))


def validate_figure_spec(spec: dict[str, Any], schema_path: Path) -> None:
    validate_schema(spec, schema_path)
    panels = spec["figure"]["panels"]
    ids = [panel["id"] for panel in panels]
    if len(ids) != len(set(ids)):
        raise ValidationError("Panel ids must be unique")
    if not set(spec["figure"]["output"]["formats"]) & {"pdf", "svg"}:
        raise ValidationError("At least one vector output is required")
    for panel in panels:
        stats = panel.get("statistics", {})
        if "significance" in stats and not stats.get("test_name"):
            raise ValidationError("Declared significance requires a test name")
        if panel.get("uncertainty") and panel["uncertainty"]["type"] == "explicit" and "value" not in panel["uncertainty"]:
            raise ValidationError("Explicit uncertainty requires its value column")


def validate_graph(graph: dict[str, Any], schema_path: Path) -> None:
    validate_schema(graph, schema_path)
    nodes = graph["nodes"]
    ids = [node["id"] for node in nodes]
    if len(ids) != len(set(ids)):
        raise ValidationError("Node ids must be unique")
    known = set(ids)
    for node in nodes:
        if node.get("semantic", True) and not node.get("evidence"):
            raise ValidationError(f"Scientific node lacks evidence: {node['id']}")
    for edge in graph["edges"]:
        if edge["source"] not in known or edge["target"] not in known:
            raise ValidationError("Edge points to a missing node")
        if not edge["relation"].strip() or not edge.get("evidence"):
            raise ValidationError("Semantic edge requires non-empty relation and evidence")
