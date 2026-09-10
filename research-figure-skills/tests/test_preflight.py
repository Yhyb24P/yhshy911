from pathlib import Path
from PIL import Image
from render import run
from preflight import run as preflight
ROOT=Path(__file__).resolve().parents[1]
def test_preflight_detects_required_checks():
 output=run(ROOT/'examples/sensitivity/figure_spec.yaml'); text=preflight(output/'figure.pdf',output/'figure_spec.yaml').read_text()
 for term in ('Width:', 'Minimum detected font', 'SVG editable text', 'Effective raster DPI', 'Panel labels:', 'Provenance exists'): assert term in text
 assert 'FAIL' not in text
def test_preflight_flags_bad_raster_and_labels():
 output=run(ROOT/'examples/sensitivity/figure_spec.yaml')
 Image.new('RGB',(30,30),'white').save(output/'figure.png',dpi=(72,72))
 report=preflight(output/'figure.pdf',output/'figure_spec.yaml').read_text()
 assert 'FAIL  Effective raster DPI' in report
 assert 'PASS  Panel labels: a' in report
