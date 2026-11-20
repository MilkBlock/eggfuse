"""Build the same native source with clean-rule mask caching and its exact audit."""
from pathlib import Path
import argparse,importlib.util,inspect,sys
HERE=Path(__file__).resolve().parent

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('out',type=Path);out=ap.parse_args().out
    prior=load('reader_build',HERE/'build.py')
    src=inspect.getsource(prior.build)
    # The main builder freezes all upstream sources; extend only this experiment's private installation.
    mark="        source=tree/base/'joint-witness/build.py'"
    assert src.count(mark)==1
    src=src.replace(mark,'''        shutil.copy2(HERE/'clean.py',local/'clean.py')
        with (local/'overlay.py').open('a') as patch:
            patch.write("\\nbase_install=install\\ndef install(crate):\\n    base_install(crate)\\n    import importlib.util\\n    spec=importlib.util.spec_from_file_location('clean_reader_bits',HERE/'clean.py')\\n    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.install(crate)\\n")
'''+mark)
    scope=dict(prior.__dict__);exec(compile(src,str(prior.__file__),'exec'),scope);scope['build'](out)
