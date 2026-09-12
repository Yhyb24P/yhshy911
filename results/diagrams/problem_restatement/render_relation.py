#!/usr/bin/env python3
"""Deterministically render the validated semantic graph as an editable SVG."""
from pathlib import Path
import hashlib
import yaml

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
GRAPH = HERE / "semantic_graph.yaml"
OUT = ROOT / "results/figures/problem_restatement_relation.svg"

def box(x, y, w, h, lines, fill="#F7FAFC"):
    tspans = "".join(
        f'<tspan x="{x+w/2}" dy="{0 if i == 0 else 27}">{line}</tspan>'
        for i, line in enumerate(lines)
    )
    start = y + h/2 - 13*(len(lines)-1)
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" stroke="#334155" stroke-width="2"/>'
            f'<text x="{x+w/2}" y="{start}" text-anchor="middle" font-family="Arial, sans-serif" font-size="20">{tspans}</text>')

def main():
    graph = yaml.safe_load(GRAPH.read_text(encoding="utf-8"))
    # This renderer only lays out the four validated concepts below; semantics remain in YAML.
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="520" viewBox="0 0 1200 520">',
             '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#334155"/></marker></defs>',
             '<rect width="1200" height="520" fill="white"/>',
             '<text x="600" y="42" text-anchor="middle" font-family="Arial, sans-serif" font-size="26" font-weight="bold">Problem inputs, states and reporting targets</text>']
    parts.append(box(400, 75, 400, 105, ['Given inputs', 'Ta(t), chi_a(t); R0, T0, X0; material properties'], '#EAF2F8'))
    parts.append(box(400, 245, 400, 105, ['State variables', 'temperature T(r,t) and moisture X(r,t)'], '#FDF2E9'))
    parts.append(box(70, 405, 410, 85, ['Q1-Q3: fixed R0', 'sampled fields; dry-time event'], '#EAF7ED'))
    parts.append(box(720, 405, 410, 85, ['Q4: measured R(t), coordinate xi', 'moving-domain fields; dry-time event'], '#EAF7ED'))
    parts += [
        '<path d="M600 180 L600 245" fill="none" stroke="#334155" stroke-width="2.5" marker-end="url(#arrow)"/>',
        '<text x="615" y="219" font-family="Arial, sans-serif" font-size="17">sets initial and boundary data</text>',
        '<path d="M500 350 L290 405" fill="none" stroke="#334155" stroke-width="2.5" marker-end="url(#arrow)"/>',
        '<path d="M700 350 L925 405" fill="none" stroke="#334155" stroke-width="2.5" marker-end="url(#arrow)"/>',
        '<text x="220" y="378" font-family="Arial, sans-serif" font-size="17">fixed-domain solve</text>',
        '<text x="824" y="378" font-family="Arial, sans-serif" font-size="17">moving-domain solve</text>',
        '</svg>'
    ]
    OUT.write_text(''.join(parts), encoding='utf-8')
    provenance = {
        'graph_id': graph['graph']['id'],
        'source': {'path': str(GRAPH), 'sha256': hashlib.sha256(GRAPH.read_bytes()).hexdigest()},
        'renderer': str(Path(__file__).resolve()),
        'manual_edits': {'declared': False},
    }
    (HERE / 'schematic_provenance.yaml').write_text(yaml.safe_dump(provenance, sort_keys=False), encoding='utf-8')

if __name__ == '__main__':
    main()
