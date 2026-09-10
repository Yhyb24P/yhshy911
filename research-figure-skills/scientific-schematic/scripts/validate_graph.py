#!/usr/bin/env python3
import argparse, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from shared.io import read_yaml
from shared.validation import validate_graph

def run(path: Path) -> None: validate_graph(read_yaml(path), ROOT / "schemas" / "semantic_graph.schema.json")
if __name__ == "__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--graph", required=True, type=Path); run(parser.parse_args().graph); print("PASS")
