"""In-process background import jobs.

No Redis/Celery: Phase 1 is a single-process, single-user tool, matching
graph-core's own "no premature optimization" stance. Job state lives only
in memory and is lost on process restart — an accepted Phase 1 gap (see
design doc's Assumptions and risks).
"""

from __future__ import annotations

import threading
import traceback
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from graph_core.client import GraphClient

from graph_explorer_api.import_pipeline.pipeline import run_import
from graph_explorer_api.import_pipeline.report import ImportReport


@dataclass
class ImportJob:
    id: str
    graph_id: str
    filename: str
    status: str = "pending"  # pending | running | done | failed
    report: Optional[ImportReport] = None
    error: Optional[str] = None


class ImportJobRunner:
    def __init__(self) -> None:
        self._jobs: dict[str, ImportJob] = {}
        self._lock = threading.Lock()

    def start(
        self,
        graph_id: str,
        filename: str,
        path: Path,
        client: GraphClient,
        on_complete: Optional[Callable[[ImportReport], None]] = None,
    ) -> ImportJob:
        job = ImportJob(id=uuid.uuid4().hex, graph_id=graph_id, filename=filename)
        with self._lock:
            self._jobs[job.id] = job

        def _run() -> None:
            with self._lock:
                job.status = "running"
            try:
                report = run_import(client, path, filename)
                with self._lock:
                    job.report = report
                    job.status = "done"
                if on_complete:
                    on_complete(report)
            except Exception as exc:  # noqa: BLE001 - surfaced via job status, not swallowed
                with self._lock:
                    job.status = "failed"
                    job.error = f"{exc}\n{traceback.format_exc()}"

        threading.Thread(target=_run, daemon=True).start()
        return job

    def get(self, job_id: str) -> Optional[ImportJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def list_for_graph(self, graph_id: str) -> list[ImportJob]:
        with self._lock:
            return [job for job in self._jobs.values() if job.graph_id == graph_id]
