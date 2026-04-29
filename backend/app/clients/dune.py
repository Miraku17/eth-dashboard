import asyncio
import logging

import httpx

DUNE_BASE_URL = "https://api.dune.com"

log = logging.getLogger(__name__)


class DuneExecutionError(RuntimeError):
    pass


class DuneClient:
    """Thin async wrapper around Dune Analytics REST API."""

    def __init__(self, http: httpx.AsyncClient, api_key: str) -> None:
        self._http = http
        self._headers = {"X-DUNE-API-KEY": api_key}

    async def execute(self, query_id: int, *, performance: str | None = None) -> str:
        # Pass `performance` as a JSON body when specified. Free-tier accounts
        # need `performance="free"` for large datasets like `dex.trades`;
        # paid tiers default to "medium" when omitted.
        kwargs: dict = {"headers": self._headers}
        if performance is not None:
            kwargs["json"] = {"performance": performance}
        r = await self._http.post(
            f"/api/v1/query/{query_id}/execute", **kwargs
        )
        r.raise_for_status()
        return r.json()["execution_id"]

    async def status(self, execution_id: str) -> str:
        r = await self._http.get(
            f"/api/v1/execution/{execution_id}/status", headers=self._headers
        )
        r.raise_for_status()
        return r.json()["state"]

    async def results(self, execution_id: str) -> list[dict]:
        r = await self._http.get(
            f"/api/v1/execution/{execution_id}/results", headers=self._headers
        )
        r.raise_for_status()
        return r.json()["result"]["rows"]

    async def execute_and_fetch(
        self,
        query_id: int,
        *,
        poll_interval_s: float = 3.0,
        max_wait_s: float = 900.0,
        performance: str | None = None,
    ) -> list[dict]:
        """Trigger a fresh execution, wait for completion, return rows."""
        execution_id = await self.execute(query_id, performance=performance)
        waited = 0.0
        while waited < max_wait_s:
            state = await self.status(execution_id)
            if state == "QUERY_STATE_COMPLETED":
                return await self.results(execution_id)
            if state in ("QUERY_STATE_FAILED", "QUERY_STATE_CANCELLED"):
                raise DuneExecutionError(f"query {query_id} ended in state {state}")
            await asyncio.sleep(poll_interval_s)
            waited += poll_interval_s
        raise DuneExecutionError(f"query {query_id} timed out after {max_wait_s}s")
