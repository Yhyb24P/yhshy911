"""SHA-256 provenance metadata."""
from datetime import datetime, timezone
import hashlib
import platform
import subprocess
from pathlib import Path
from typing import Any
import matplotlib, numpy, pandas, yaml


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_metadata(root: Path) -> dict[str, Any]:
    try:
        commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, text=True, capture_output=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "-C", str(root), "status", "--porcelain"], check=True, text=True, capture_output=True).stdout.strip())
        return {"commit": commit, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def write_provenance(output: Path, figure_id: str, source: Path, spec: Path, renderer: str, repo_root: Path) -> None:
    payload = {"figure_id": figure_id, "sources": [{"path": str(source), "sha256": sha256(source)}], "spec": {"path": str(spec), "sha256": sha256(spec)}, "renderer": {"script": renderer, "version": "0.1.0"}, "environment": {"python": platform.python_version(), "matplotlib": matplotlib.__version__, "numpy": numpy.__version__, "pandas": pandas.__version__}, "git": git_metadata(repo_root), "generated_at": datetime.now(timezone.utc).isoformat(), "manual_edits": {"declared": False}}
    with output.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=True)
