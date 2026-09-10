#!/usr/bin/env python3
"""Evidence-constrained semantic graph to editable SVG."""
import argparse, hashlib, sys
from datetime import datetime, timezone
from pathlib import Path
import yaml
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(Path(__file__).parent))
from shared.io import read_yaml
from shared.validation import validate_graph
from layout import positions

def run(graph_path: Path) -> Path:
    graph_path=graph_path.resolve(); graph=read_yaml(graph_path); validate_graph(graph, ROOT / "schemas" / "semantic_graph.schema.json")
    output=graph_path.parent / "schematic.svg"; pos=positions(graph["nodes"]); width=max(800, 180*(min(4,len(graph["nodes"]))))
    pieces=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="300" viewBox="0 0 {width} 300"><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z"/></marker></defs><text x="20" y="25" font-family="Arial" font-size="16">{graph["graph"]["title"]}</text>']
    for edge in graph["edges"]:
        x1,y1=pos[edge["source"]]; x2,y2=pos[edge["target"]]; pieces.append(f'<line x1="{x1+65}" y1="{y1}" x2="{x2-65}" y2="{y2}" stroke="#333" marker-end="url(#arrow)"/><text x="{(x1+x2)/2}" y="{(y1+y2)/2-8}" text-anchor="middle" font-size="10">{edge["relation"]}</text>')
    for node in graph["nodes"]:
        x,y=pos[node["id"]]; pieces.append(f'<rect x="{x-65}" y="{y-25}" width="130" height="50" rx="5" fill="white" stroke="#222"/><text x="{x}" y="{y+4}" text-anchor="middle" font-family="Arial" font-size="12">{node["label"]}</text>')
    output.write_text("".join(pieces)+"</svg>",encoding="utf-8")
    provenance={"graph_id":graph["graph"]["id"],"source":{"path":str(graph_path),"sha256":hashlib.sha256(graph_path.read_bytes()).hexdigest()},"generated_at":datetime.now(timezone.utc).isoformat(),"manual_edits":{"declared":False}}
    (graph_path.parent/"schematic_provenance.yaml").write_text(yaml.safe_dump(provenance,sort_keys=False),encoding="utf-8")
    (graph_path.parent/"schematic-audit-report.md").write_text("# Schematic Audit Report\n\nPASS  Schema and semantic evidence validation completed.\n\nMANUAL_CHECK  Evidence supports declared relationships; scientific truth requires domain review.\n",encoding="utf-8")
    return output
if __name__ == "__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--graph",required=True,type=Path); print(run(parser.parse_args().graph))
