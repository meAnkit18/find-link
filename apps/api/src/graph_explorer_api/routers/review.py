from __future__ import annotations

from fastapi import APIRouter, Depends

from graph_explorer_api.dependencies import get_clients, get_graph_or_404, get_registry
from graph_explorer_api.graph_clients import GraphClientCache
from graph_explorer_api.graph_registry import GraphRegistry
from graph_explorer_api.repositories.review_queue_repo import ReviewQueueRepository

router = APIRouter(prefix="/api/review-queue", tags=["review"])


def _get_repo(
    graph_id: str,
    registry: GraphRegistry,
    clients: GraphClientCache,
) -> ReviewQueueRepository:
    graph = get_graph_or_404(graph_id, registry)
    client = clients.for_space(graph.space)
    return ReviewQueueRepository(client)


@router.get("")
def list_review_items(
    graph_id: str,
    queue_type: str | None = None,
    registry: GraphRegistry = Depends(get_registry),
    clients: GraphClientCache = Depends(get_clients),
):
    repo = _get_repo(graph_id, registry, clients)
    return repo.list_pending(queue_type)


@router.post("/{review_id}/approve")
def approve_review(
    graph_id: str,
    review_id: str,
    reviewed_by: str,
    reason: str | None = None,
    registry: GraphRegistry = Depends(get_registry),
    clients: GraphClientCache = Depends(get_clients),
):
    repo = _get_repo(graph_id, registry, clients)
    repo.approve(review_id, reviewed_by, reason)
    return {"status": "approved"}


@router.post("/{review_id}/reject")
def reject_review(
    graph_id: str,
    review_id: str,
    reviewed_by: str,
    reason: str,
    registry: GraphRegistry = Depends(get_registry),
    clients: GraphClientCache = Depends(get_clients),
):
    repo = _get_repo(graph_id, registry, clients)
    repo.reject(review_id, reviewed_by, reason)
    return {"status": "rejected"}
