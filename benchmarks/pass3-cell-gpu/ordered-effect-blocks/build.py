"""Link ordered effect blocks into the composed learned CPU backend."""
import argparse
import hashlib
import json
import os
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("composed_build", HERE.parent/"composed-cpu/build.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("--writers",action="store_true")
    args=parser.parse_args()
    if args.writers:
        os.environ["EGGFUSE_ORDERED_WRITE_STUDY"]="1"
    else:
        os.environ.pop("EGGFUSE_ORDERED_WRITE_STUDY",None)
    base.joint.build(args.out, True, True, True, cli_allocator=True,
                     extensions=(*base.EXTENSIONS, HERE.name))
    if args.writers:
        manifest=args.out/"build.json"
        data=json.loads(manifest.read_bytes())
        data["ordered_writer_source_sha256"]=hashlib.sha256((HERE/"writer.py").read_bytes()).hexdigest()
        manifest.write_text(json.dumps(data,indent=1)+"\n")
