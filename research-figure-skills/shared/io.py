"""Strict, local-only structured-file readers."""
from pathlib import Path
from typing import Any
import pandas as pd
import yaml
from .exceptions import SourceIntegrityError


def read_yaml(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise SourceIntegrityError(f"Missing input: {path}")
    with path.open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise SourceIntegrityError(f"Malformed YAML mapping: {path}")
    return value


def read_table(path: str | Path, source_type: str) -> pd.DataFrame:
    path = Path(path)
    if not path.is_file():
        raise SourceIntegrityError(f"Missing source data: {path}")
    if source_type == "csv":
        return pd.read_csv(path)
    if source_type == "tsv":
        return pd.read_csv(path, sep="\t")
    raise SourceIntegrityError(f"Unsupported source type: {source_type}")
