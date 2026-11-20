"""Build and check both concrete session paths before starting the already specified timing matrix."""
import argparse
from pathlib import Path
import subprocess
import sys
HERE=Path(__file__).resolve().parent
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('exp','build','out'):p.add_argument(key,type=Path)
    a=p.parse_args()
    subprocess.run([sys.executable,HERE/'build.py',a.build,'--small-forward'],check=True)
    ordinary=a.build/'control/session';compact=a.build/'session'
    assert ordinary.is_file() and compact.is_file()
    subprocess.run([sys.executable,HERE/'forward_study.py',ordinary,compact,a.exp,a.out],check=True)
