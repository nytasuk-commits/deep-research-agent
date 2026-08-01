"""
Multi-endpoint LLM router for deep-research-agent.

Routes requests across multiple endpoints, tracking health and enforcing
per-endpoint concurrency limits. Health snapshots are taken at query start;
no mid-query rebalancing occurs.
"""

import asyncio
import os
import time
import logging
import contextlib
import pathlib
from typing import Optional, List, Tuple

import httpx

import config
from agent_framework.openai import OpenAIChatCompletionClient


# --- Module-level singleton accessors ---

_router: Optional["EndpointRouter"] = None

def get_router() -> "EndpointRouter":
    """Lazily create the module-level singleton and return it."""
    global _router
    if _router is None:
        _router = EndpointRouter()
    return _router

async def aclose_router() -> None:
    """
    If the singleton exists, await its aclose() and set the module global back
    to None. Safe to call when no router exists.
    """
    global _router
    if _router is not None:
        await _router.aclose()
        _router = None


# --- Logging ---

_logger: Optional[logging.Logger] = None

def _get_router_logger() -> logging.Logger:
    """Get or create the module logger with file handler."""
    global _logger
    if _logger is not None:
        return _logger

    logger_name = "deep_research_agent.router"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)

    # Guard against duplicate handlers on repeated imports
    if logger.handlers:
        logger.propagate = False
        return logger

    log_dir = pathlib.Path.home() / f".{config.APP_NAME}" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "router.log"

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False

    _logger = logger
    return logger


# --- Backoff schedule ---

_BACKOFF: Tuple[int, ...] = (10, 30, 60, 60, 60, 60)
_MAX_FAILS = 6


class _EndpointState:
    """
    Holds the state for a single endpoint URL.

    Fields are set in __init__(self, url: str).
    """

    def __init__(self, url: str):
        self.url = url
        self.raw: Optional["AsyncOpenAI"] = None  # type: ignore[name-defined]
        self.client: Optional[OpenAIChatCompletionClient] = None
        self.inflight = 0           # tasks currently being served by this endpoint
        self.peak_inflight = 0      # highest simultaneous inflight seen
        self.up = True              # OPTIMISTIC: unknown means "candidate for priming"
        self.primed = False
        self.fail_count = 0
        self.permanently_down = False
        self.next_probe_at = 0.0    # time.monotonic() deadline
        self.served = 0             # count of tasks served, for diagnostics


class EndpointRouter:
    """
    Manages multiple LLM endpoints with health tracking and per-endpoint
    concurrency limits.

    Health snapshots are taken at query start; no mid-query rebalancing occurs.
    Global concurrency = (number of up endpoints) * per_endpoint_cap.
    """

    def __init__(self):
        """
        Initialize the router. Builds endpoint clients but does NOT perform
        any network I/O.
        """
        api_cfg = config.cfg.get("api", {})
        self._urls: List[str] = api_cfg.get("openai_base_urls", [])
        if not self._urls:
            self._urls = ["http://localhost:8080/v1"]

        self._model: str = api_cfg.get("openai_model", "local-model")
        self._cap: int = config.cfg.get("settings", {}).get("concurrency", {}).get("per_endpoint_cap", 1)
        if self._cap < 1:
            self._cap = 1

        # Build endpoints dict in config order
        self._endpoints: dict[str, _EndpointState] = {}
        for url in self._urls:
            state = _EndpointState(url)
            self._build_endpoint_clients(state)
            self._endpoints[url] = state

        self._snapshot_urls: List[str] = []
        self._concurrency: int = self._cap
        self._peak_total_inflight = 0   # highest sum of inflight across all endpoints
        self._poll_task: Optional[asyncio.Task[None]] = None
        self._closed: bool = False

        self._logger = _get_router_logger()

    def _build_endpoint_clients(self, state: _EndpointState) -> None:
        """
        Build the raw and client objects for an endpoint, matching the pattern
        from orchestrator.py's _build_client().
        """
        from openai import AsyncOpenAI

        raw = AsyncOpenAI(
            base_url=state.url,
            api_key=os.getenv("OPENAI_API_KEY", "dummy"),
            timeout=httpx.Timeout(1800.0, connect=15.0, read=300.0),
        )
        state.raw = raw
        state.client = OpenAIChatCompletionClient(model=self._model, async_client=raw)

    def current_concurrency(self) -> int:
        """Return the current global concurrency limit."""
        return self._concurrency

    def orchestrator_client(self) -> OpenAIChatCompletionClient:
        """
        Return the OpenAIChatCompletionClient of the first URL in
        self._snapshot_urls.

        The orchestrator agent is pinned to one endpoint for the whole query.
        If snapshot_and_prime() has not been called or no endpoints are up,
        raise RuntimeError with a clear message.
        """
        if not self._snapshot_urls:
            raise RuntimeError(
                "No LLM endpoints available: snapshot_and_prime() must be "
                "called first to prime and discover healthy endpoints."
            )
        return self._endpoints[self._snapshot_urls[0]].client

    def endpoint_count(self) -> int:
        """Return the number of up endpoints in the current snapshot."""
        return len(self._snapshot_urls)

    async def snapshot_and_prime(
        self,
        notify: Optional[asyncio.Callable[[str], None]] = None
    ) -> Tuple[List[str], int]:
        """
        Take a health snapshot of all endpoints, prime unprimed candidates,
        and update the concurrency limit.

        Args:
            notify: Optional async callable taking a single string message.
                   Used to surface one message per endpoint (greeting or failure).
                   If None, log only.

        Returns:
            Tuple of (list of up endpoint URLs, derived global concurrency)

        Raises:
            RuntimeError: If no endpoints are available after priming.
        """
        # 1. Start the poller if not already running
        self._ensure_poller()

        # 2. Candidates = every endpoint where (not permanently_down) and up is True
        candidates = [
            state for state in self._endpoints.values()
            if not state.permanently_down and state.up
        ]

        # 3. For every candidate with primed == False, prime concurrently
        async def _prime_if_needed(state: _EndpointState) -> Optional[str]:
            """Prime an endpoint and return a message string."""
            if state.primed:
                return None
            try:
                reply = await self._prime(state)
                state.primed = True
                state.up = True
                state.fail_count = 0
                preview = reply[:200] + ("..." if len(reply) > 200 else "")
                msg = f"[{state.url}] primed OK: {preview}"
                return msg
            except Exception as e:
                state.primed = False
                state.up = False
                state.fail_count += 1
                if state.fail_count >= _MAX_FAILS:
                    state.permanently_down = True
                    self._logger.info(
                        f"[{state.url}] PRIME FAILED permanently: {e}"
                    )
                else:
                    # Set next_probe_at from backoff schedule
                    idx = min(state.fail_count - 1, len(_BACKOFF) - 1)
                    state.next_probe_at = time.monotonic() + _BACKOFF[idx]
                msg = f"[{state.url}] PRIME FAILED — excluded from this query: {e}"
                return msg

        # Gather priming tasks for unprimed candidates
        tasks_to_prime = [
            (state, asyncio.create_task(_prime_if_needed(state)))
            for state in candidates
            if not state.primed
        ]

        if tasks_to_prime:
            results = await asyncio.gather(
                *[t[1] for t in tasks_to_prime],
                return_exceptions=True
            )
            for i, ((state, task), result) in enumerate(zip(tasks_to_prime, results)):
                # Handle exceptions from gather
                if isinstance(result, Exception):
                    msg = f"[{state.url}] PRIME FAILED — excluded from this query: {result}"
                else:
                    msg = result
                if msg is not None:
                    self._logger.info(msg)
                    if notify is not None:
                        await notify(msg)

        # 4. Snapshot = [url for endpoints that are up, not permanently_down, and primed]
        self._snapshot_urls = [
            url for url in self._urls
            if (
                url in self._endpoints and
                self._endpoints[url].up and
                not self._endpoints[url].permanently_down and
                self._endpoints[url].primed
            )
        ]

        # 5. If empty, raise RuntimeError
        if not self._snapshot_urls:
            raise RuntimeError(
                "No LLM endpoints available: all configured endpoints failed priming."
            )

        # 6. Update concurrency
        self._concurrency = len(self._snapshot_urls) * self._cap

        # 7. Log snapshot and return
        self._logger.info(
            f"Snapshot: {len(self._snapshot_urls)} endpoint(s), "
            f"global concurrency = {self._concurrency}"
        )

        return list(self._snapshot_urls), self._concurrency

    async def _prime(self, state: _EndpointState) -> str:
        """
        Issue a bare completion to prime an endpoint.

        Returns the reply text (first choice message content).
        600s timeout because cold LM Studio must load model into VRAM.
        """
        resp = await state.raw.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": "Reply with the single word: ready"}],
            max_tokens=16,
            timeout=600.0,
        )
        return resp.choices[0].message.content or ""

    @contextlib.asynccontextmanager
    async def acquire(self, task_name: str = None):
        """Yield the client of the least-loaded endpoint. Never blocks."""
        ep = self._select_endpoint()
        ep.inflight += 1
        ep.served += 1
        if ep.inflight > ep.peak_inflight:
            ep.peak_inflight = ep.inflight
        total = sum(self._endpoints[u].inflight for u in self._snapshot_urls)
        if total > self._peak_total_inflight:
            self._peak_total_inflight = total
        self._logger.info(
            f"ACQUIRE {ep.url} task='{task_name or '<unnamed>'}' "
            f"inflight={ep.inflight}/{self._cap} total={total}/{self._concurrency} "
            f"served={ep.served} peak_ep={ep.peak_inflight} peak_total={self._peak_total_inflight}"
        )
        try:
            yield ep.client
        finally:
            ep.inflight -= 1
            total_after = sum(self._endpoints[u].inflight for u in self._snapshot_urls)
            self._logger.info(
                f"RELEASE {ep.url} task='{task_name or '<unnamed>'}' "
                f"inflight={ep.inflight}/{self._cap} total={total_after}/{self._concurrency}"
            )

    def _select_endpoint(self) -> _EndpointState:
        """Pick the endpoint with the fewest in-flight tasks.

        Never blocks and never waits: the global semaphore in orchestrator.py
        is the sole admission-control primitive. This method only decides WHICH
        endpoint serves an already-admitted task. Ties break toward the earlier
        endpoint in config order, which keeps single-endpoint behaviour
        identical to the pre-router code path.
        """
        if not self._snapshot_urls:
            raise RuntimeError(
                "No endpoint snapshot: snapshot_and_prime() must be called "
                "before serving tasks."
            )
        eps = [self._endpoints[u] for u in self._snapshot_urls]
        return min(eps, key=lambda e: e.inflight)

    def inflight_snapshot(self) -> dict:
        """Current in-flight count per endpoint, for logging/diagnostics."""
        return {u: self._endpoints[u].inflight for u in self._snapshot_urls}

    def peak_summary(self) -> dict:
        """Peak concurrency observed so far, for diagnostics."""
        return {
            "per_endpoint": {u: self._endpoints[u].peak_inflight for u in self._snapshot_urls},
            "total": self._peak_total_inflight,
            "derived_global_concurrency": self._concurrency,
        }

    def _ensure_poller(self) -> None:
        """If poll_task is None and not closed, create the poll task."""
        if self._poll_task is None and not self._closed:
            self._poll_task = asyncio.create_task(self._poll_loop())

    def _mark_probe_failed(self, state: _EndpointState) -> None:
        """
        Mark an endpoint as failed (synchronous, no awaits).

        Updates state.up=False, state.primed=False, increments fail_count,
        sets next_probe_at from backoff schedule. If max fails reached,
        marks permanently_down.
        """
        state.up = False
        state.primed = False
        state.fail_count += 1
        if state.fail_count >= _MAX_FAILS:
            state.permanently_down = True
            self._logger.info(
                f"[{state.url}] marked permanently DOWN after {_MAX_FAILS} failures"
            )
        else:
            idx = min(state.fail_count - 1, len(_BACKOFF) - 1)
            state.next_probe_at = time.monotonic() + _BACKOFF[idx]

    def _mark_up(self, state: _EndpointState) -> None:
        """
        Mark an endpoint as up (synchronous, no awaits).

        Updates state.up=True, resets fail_count to 0 and next_probe_at.
        Does NOT set primed; a recovered endpoint must be re-primed before use.
        """
        state.up = True
        state.fail_count = 0
        state.next_probe_at = 0.0

    async def _probe(self, state: _EndpointState) -> bool:
        """
        Cheap liveness check that does NOT load the model.

        HTTP GET on {url.rstrip('/')}/models using short-lived client.
        Return True on HTTP 2xx, False otherwise.
        """
        url = state.url.rstrip("/") + "/models"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                return 200 <= resp.status_code < 300
        except Exception:
            return False

    async def _poll_loop(self) -> None:
        """
        Background poller that periodically checks down endpoints.

        Sleeps 5 seconds between iterations. For each endpoint not up and not
        permanently_down, probes it. On success marks up; on failure applies
        backoff. Never dies silently.
        """
        while True:
            await asyncio.sleep(5)
            now = time.monotonic()
            for state in list(self._endpoints.values()):
                if state.permanently_down or state.up:
                    continue
                if now < state.next_probe_at:
                    continue
                ok = await self._probe(state)
                if ok:
                    self._mark_up(state)
                else:
                    self._mark_probe_failed(state)

    async def aclose(self) -> None:
        """
        Close the router: cancel poller and close all endpoint clients.

        Idempotent: a second call must not raise.
        """
        self._closed = True

        # Cancel poll task if present
        if self._poll_task is not None:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

        # Log peak summary at teardown (wrap in try/except to never block)
        try:
            self._logger.info(f"PEAK SUMMARY: {self.peak_summary()}")
        except Exception:
            pass

        # Close all raw clients
        for state in self._endpoints.values():
            if state.raw is not None:
                try:
                    await state.raw.close()
                except Exception:
                    # One failure should not block others
                    pass
