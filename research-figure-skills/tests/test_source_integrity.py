from pathlib import Path
import pytest
import matplotlib.pyplot as plt
from shared.exceptions import ValidationError
from shared.io import read_yaml, read_table
from renderers.common import render_panel
ROOT=Path(__file__).resolve().parents[1]
@pytest.mark.parametrize('field',["x","y"])
def test_missing_referenced_column_fails(field):
 panel=read_yaml(ROOT/'examples/sensitivity/figure_spec.yaml')['figure']['panels'][0]; panel[field]='not_a_column'
 fig,ax=plt.subplots()
 with pytest.raises(ValidationError): render_panel(ax,read_table(ROOT/'examples/sensitivity/data.csv','csv'),panel,{})
 plt.close(fig)
