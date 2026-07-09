import sys
from pathlib import Path
p = str(Path(__file__).parent.parent)
if p not in sys.path:
    sys.path.insert(0, p)
