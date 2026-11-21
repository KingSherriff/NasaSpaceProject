"""Command line (run from AnalogEngine/):

    python -m analog_engine                      # every step: download planets base score frontend
    python -m analog_engine base score frontend  # only these steps (always run in pipeline order)
    python -m analog_engine validate [file]      # check frontend_cells.json against the contract
    python -m analog_engine sources              # list base-table layers and their source URLs
"""

import argparse
import sys
from pathlib import Path

from .config import RAW
from .pipeline import STEPS, run


def main() -> int:
    p = argparse.ArgumentParser(prog="python -m analog_engine", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    _ = p.add_argument("steps", nargs="*", help=f"steps {list(STEPS)}, or 'validate [file]', or 'sources'")
    args = p.parse_args()

    if args.steps[:1] == ["validate"]:
        from .frontend import OUT, validate_file

        return 0 if validate_file(Path(args.steps[1]) if len(args.steps) > 1 else OUT) else 1
    if args.steps[:1] == ["sources"]:
        from .base_table import build_base_engine

        print(build_base_engine(RAW).sources().to_string(index=False))
        return 0
    run(args.steps or STEPS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
