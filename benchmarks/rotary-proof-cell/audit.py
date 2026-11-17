"""Audit saved inference checkpoints with NumPy only; no model execution or repair."""
import argparse
import json
import sys
from pathlib import Path
import numpy as np
from contract import audit_result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('checkpoint', type=Path)
    args = parser.parse_args()
    with np.load(args.checkpoint, allow_pickle=False) as data:
        result = audit_result(data['cases'], data['positions'], data,
                              data['decoder_weight'], data['decoder_bias'])
    print(json.dumps(result, indent=2))
    sys.exit(0 if result['accepted'] else 1)


if __name__ == '__main__':
    main()
