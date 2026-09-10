# Research Figure Skills V1

An offline, evidence-constrained toolkit for reproducible quantitative figures, semantic schematics, and pre-submission visual QA. It deliberately fails closed for absent data, malformed contracts, missing columns, unsupported plots, and unsupported semantic edges.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Or run `pip install -r requirements.txt`.

## Examples

```bash
python nature-figure/scripts/render.py --spec examples/sensitivity/figure_spec.yaml
python scientific-schematic/scripts/render_svg.py --graph examples/architecture/semantic_graph.yaml
python figure-preflight/scripts/preflight.py examples/sensitivity/output/figure.pdf --spec examples/sensitivity/output/figure_spec.yaml --profile nature
pytest -q
```

`examples/sensitivity/data.csv` is a **synthetic test fixture, not scientific evidence**. Replace it with traceable source data and a claim-specific figure contract for research use.

## Skills

Project-local installation is preferred: copy this repository's `nature-figure/`, `scientific-schematic/`, and `figure-preflight/` folders into `.agents/skills/`. A user-level installation may use `~/.codex/skills/`; paths vary across platforms.

`nature-figure` renders only declared source values and does not infer statistical quantities. `scientific-schematic` requires evidence for each scientific node and edge. `figure-preflight` audits files but cannot prove scientific, causal, or biological correctness.
