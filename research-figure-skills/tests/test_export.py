from pathlib import Path
import fitz
from PIL import Image
from lxml import etree
from render import run
ROOT=Path(__file__).resolve().parents[1]
def test_exports_parse():
 output=run(ROOT/'examples/sensitivity/figure_spec.yaml')
 assert all((output/f'figure.{x}').stat().st_size>1000 for x in ('pdf','svg','png'))
 assert fitz.open(output/'figure.pdf').page_count==1; assert etree.parse(str(output/'figure.svg')).xpath("//*[local-name()='text']")
 with Image.open(output/'figure.png') as im: im.verify()
