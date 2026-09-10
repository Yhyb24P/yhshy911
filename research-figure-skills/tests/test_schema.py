from pathlib import Path
import pytest
from shared.exceptions import ValidationError
from shared.io import read_yaml
from shared.validation import validate_figure_spec
from shared.io import read_table
from shared.exceptions import SourceIntegrityError
ROOT=Path(__file__).resolve().parents[1]
def test_valid_spec(): validate_figure_spec(read_yaml(ROOT/'examples/sensitivity/figure_spec.yaml'),ROOT/'schemas/figure_spec.schema.json')
@pytest.mark.parametrize('mutator',[lambda s:s['figure']['source'].pop('path'),lambda s:s['figure']['panels'][0].update(type='magic'),lambda s:s['figure']['panels'][0].pop('x')])
def test_invalid_specs_fail(mutator):
 s=read_yaml(ROOT/'examples/sensitivity/figure_spec.yaml'); mutator(s)
 with pytest.raises(ValidationError): validate_figure_spec(s,ROOT/'schemas/figure_spec.schema.json')
def test_missing_source_fails_closed():
 with pytest.raises(SourceIntegrityError): read_table(ROOT/'tests/fixtures/missing.csv','csv')
