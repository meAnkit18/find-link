import os
import sys
import tempfile
from pathlib import Path

# Point the evidence DB at a throwaway temp file before any project import,
# so running tests can never touch a developer's real evidence_store.db.
os.environ["EVIDENCE_DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test_evidence.db"

p = str(Path(__file__).parent.parent)
if p not in sys.path:
    sys.path.insert(0, p)
