from pathlib import Path
import importlib.util
import sys
from overlay import install
HERE=Path(__file__).resolve().parent
def build(out):
    root=HERE.parent/'ordinary-witness';sys.path.insert(0,str(root))
    spec=importlib.util.spec_from_file_location('base_ordinary_build',root/'build.py')
    b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
    prior=b.install
    def both(crate):prior(crate);install(crate)
    b.install=both;b.build(out)
if __name__=='__main__':build(Path(sys.argv[1]))
