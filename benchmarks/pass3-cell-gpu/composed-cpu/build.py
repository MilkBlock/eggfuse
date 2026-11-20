"""Link the single-parent header view and derived arithmetic port options into one CPU binary."""
import argparse
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "joint-witness"))
import build as joint

EXTENSIONS = (
    "incremental-neural-index", "baked-port-codes", "adaptive-row-policy", "witness-production-profile",
    "multi-root-pages", "transaction-guards", "single-signature-frontier", "integrated-cpu-policy",
    "learned-prefix-feasibility", "projected-single-verifier", "prepared-port-blocks", "learned-atom-constraints",
    "tiered-port-projections", "complete-generation", "pair-source-frontier", "lazy-equation-ports",
    "published-single-headers",
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    joint.build(parser.parse_args().out, True, True, True, cli_allocator=True, extensions=EXTENSIONS)
