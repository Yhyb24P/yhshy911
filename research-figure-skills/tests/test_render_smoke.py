from pathlib import Path
from render import run
ROOT=Path(__file__).resolve().parents[1]
def test_render_smoke():
 output=run(ROOT/'examples/sensitivity/figure_spec.yaml')
 assert (output/'figure.pdf').is_file()
