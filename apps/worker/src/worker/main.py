"""Background job worker for the Graph Intelligence Platform.

Claims pending jobs from NebulaGraph, executes them, and updates status.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone

from graph_core.client import GraphClient
from graph_core.config import GraphConfig


class JobWorker:
    """Simple polling worker that claims and executes background jobs."""

    def __init__(self, client: GraphClient, worker_id: str | None = None) -> None:
        self.client = client
        self.worker_id = worker_id or f"worker:{uuid.uuid4().hex[:8]}"

    def claim_job(self) -> dict | None:
        now = datetime.now(timezone.utc).isoformat()
        ngql = (
            'LOOKUP ON background_job '
            'WHERE background_job.status == "pending" '
            'AND (background_job.lease_owner IS NULL '
            'OR background_job.lease_expires_at < datetime("' + now + '")) '
            'YIELD id(vertex) AS id, properties(vertex) AS props '
            '| LIMIT 1'
        )
        result = self.client.execute_raw(ngql)
        if not result.rows:
            return None

        row = result.rows[0]
        job_id = row["id"]
        props = row["props"]

        lease_expires = datetime.now(timezone.utc).isoformat()
        update_ngql = (
            f'UPDATE vertex ON background_job "{job_id}" '
            f'SET background_job.lease_owner = "{self.worker_id}", '
            f'background_job.lease_expires_at = datetime("{lease_expires}"), '
            f'background_job.status = "running", '
            f'background_job.started_at = datetime("{now}"), '
            f'background_job.attempt = {int(props.get("attempt", 0)) + 1}'
        )
        self.client.execute_raw(update_ngql)

        verify = self.client.execute_raw(
            f'FETCH PROP ON background_job "{job_id}" YIELD VERTEX AS v'
        )
        if not verify.rows:
            return None
        v = verify.rows[0].get("v")
        if v is None:
            return None
        tag_data = v.tags.get("background_job", {})
        if tag_data.get("lease_owner") != self.worker_id:
            return None

        return {"job_id": job_id, **tag_data}

    def complete_job(self, job_id: str, result: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.client.execute_raw(
            f'UPDATE vertex ON background_job "{job_id}" '
            f'SET background_job.status = "completed", '
            f'background_job.result_json = {json.dumps(json.dumps(result))}, '
            f'background_job.completed_at = datetime("{now}"), '
            f'background_job.updated_at = datetime("{now}")'
        )

    def fail_job(self, job_id: str, error: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.client.execute_raw(
            f'UPDATE vertex ON background_job "{job_id}" '
            f'SET background_job.status = "failed", '
            f'background_job.error = {json.dumps(error)}, '
            f'background_job.completed_at = datetime("{now}"), '
            f'background_job.updated_at = datetime("{now}")'
        )

    def execute_job(self, job: dict) -> dict:
        job_type = job.get("job_type", "unknown")
        payload = json.loads(job.get("payload_json", "{}"))

        if job_type == "csv_import":
            return self._execute_csv_import(payload)
        elif job_type == "risk_recompute":
            return self._execute_risk_recompute(payload)
        return {"error": f"unknown job type: {job_type}"}

    def _execute_csv_import(self, payload: dict) -> dict:
        return {"status": "not_implemented", "payload": payload}

    def _execute_risk_recompute(self, payload: dict) -> dict:
        return {"status": "not_implemented", "payload": payload}

    def run_once(self) -> bool:
        job = self.claim_job()
        if job is None:
            return False
        try:
            result = self.execute_job(job)
            self.complete_job(job["job_id"], result)
        except Exception as exc:
            self.fail_job(job["job_id"], str(exc))
        return True

    def run_forever(self, poll_interval: float = 5.0) -> None:
        while True:
            self.run_once()
            time.sleep(poll_interval)


def main() -> None:
    config = GraphConfig(
        hosts=["127.0.0.1:9669"],
        user="root",
        password="nebula",
        space="intelligence_graph",
    )
    client = GraphClient(config)
    client.connect()
    worker = JobWorker(client)
    worker.run_forever()


if __name__ == "__main__":
    main()
