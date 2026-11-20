"""Build the resident CPU runtime and the online deferred request experiment."""
import argparse
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'joint-witness'))
import build as joint

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    extensions = ('incremental-neural-index', 'baked-port-codes', 'adaptive-row-policy', 'request-transactions')
    joint.build(parser.parse_args().out, True, True, True, cli_allocator=True, extensions=extensions)
