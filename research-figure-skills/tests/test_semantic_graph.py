from pathlib import Path
import pytest
from shared.exceptions import ValidationError
from shared.io import read_yaml
from shared.validation import validate_graph
from render_svg import run
ROOT=Path(__file__).resolve().parents[1]
def test_valid_graph_renders(): assert run(ROOT/'examples/architecture/semantic_graph.yaml').is_file()
@pytest.mark.parametrize('kind',["node", "edge_target", "edge_evidence"])
def test_bad_graph_fails(kind):
 graph=read_yaml(ROOT/'examples/architecture/semantic_graph.yaml')
 if kind=='node': graph['nodes'][0].pop('evidence')
 elif kind=='edge_target': graph['edges'][0]['target']='missing'
 else: graph['edges'][0].pop('evidence')
 with pytest.raises(ValidationError): validate_graph(graph,ROOT/'schemas/semantic_graph.schema.json')
def test_layout_node_allowed():
 graph=read_yaml(ROOT/'examples/architecture/semantic_graph.yaml'); graph['nodes'].append({'id':'note','label':'note','type':'annotation','semantic':False}); validate_graph(graph,ROOT/'schemas/semantic_graph.schema.json')
