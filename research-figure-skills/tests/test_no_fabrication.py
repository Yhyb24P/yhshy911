from pathlib import Path
import matplotlib.pyplot as plt
from shared.io import read_yaml, read_table
from renderers.common import render_panel
ROOT=Path(__file__).resolve().parents[1]
def test_no_undeclared_errorbars_or_groups():
 spec=read_yaml(ROOT/'examples/sensitivity/figure_spec.yaml')['figure']['panels'][0]; spec.pop('group')
 fig,ax=plt.subplots(); render_panel(ax,read_table(ROOT/'examples/sensitivity/data.csv','csv'),spec,{})
 assert not ax.containers and not ax.get_legend(); assert not ax.texts; plt.close(fig)
