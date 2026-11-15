"""Standalone check of public/data/frontend_cells.json (needs numpy only, no parquet).

Run:  python scripts/validate_frontend.py [path/to/frontend_cells.json]
Exit code 0 = file matches the contract, 1 = inconsistency (message printed).
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from export_frontend import validate        # same rules the exporter uses; imports pandas/scipy
except ImportError as e:
    sys.exit(f"Run inside the spaceapps env (mamba run -n spaceapps python ...): {e}")

path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "public" / "data" / "frontend_cells.json"
data = json.loads(path.read_text())
try:
    validate(data)
except AssertionError as e:
    print(f"FAIL {path.name}: {e}")
    sys.exit(1)
print(f"OK   {path.name}: {data['meta']['n_cells']:,} cells, mocked = {data['meta']['mocked'] or 'none'}")
