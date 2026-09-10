#!/usr/bin/env python3
import argparse, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
from shared.io import read_yaml
from shared.validation import validate_figure_spec
if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('--spec',required=True,type=Path); validate_figure_spec(read_yaml(p.parse_args().spec),ROOT/'schemas'/'figure_spec.schema.json'); print('PASS')
