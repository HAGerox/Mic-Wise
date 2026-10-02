"""Prometheus scrape endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

router = APIRouter()


@router.get("/metrics", include_in_schema=False)
async def read_metrics(request: Request) -> Response:
	"""Serve the latest collected metrics in the Prometheus text format."""
	metrics = request.app.state.metrics
	metrics.refresh_runtime_state(request.app.state)
	return Response(content=metrics.render(), media_type=metrics.content_type)
