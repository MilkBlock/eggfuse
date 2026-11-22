from pathlib import Path
import sys

here = Path(__file__).resolve().parent
sys.path.insert(0, str(here.parent/'joint-witness'))
from build import build

if __name__ == '__main__':
    build(Path(sys.argv[1]), True, True, True, extensions=(here.name,))
