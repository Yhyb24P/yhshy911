import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'nature-figure'/'scripts')); sys.path.insert(0,str(ROOT/'figure-preflight'/'scripts')); sys.path.insert(0,str(ROOT/'scientific-schematic'/'scripts'))
