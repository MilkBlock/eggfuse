"""Extend the composed CPU study with a borrowed production root receipts."""
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec
import argparse

HERE = Path(__file__).resolve().parent
spec = spec_from_file_location('composed_build', HERE.parent/'composed-cpu/build.py')
driver = module_from_spec(spec)
spec.loader.exec_module(driver)

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('out', type=Path)
    driver.joint.build(p.parse_args().out, True, True, True, cli_allocator=True,
                       extensions=(*driver.EXTENSIONS, HERE.name))
