# Multi-Endpoint Router

**Status:** Complete — implemented, unit-tested, live-validated
**Priority:** Medium (throughput optimization, not correctness)
**Branch:** `multi-endpoint-router` (8 commits, `9ce5a0a` → `ad6e48d`)
**Depends on:** None
**Blocks:** None

> **This document is an as-built record.** It was originally a design spec. Two
> design decisions changed during implementation — the per-endpoint semaphore
> and the TUI primer removal — and both are documented in
> "Deviations from the original design" below, with the reasoning. The rest of
> the document describes what actually exists in the code.

## Problem

All agents shared a single LM Studio endpoint (`_build_client` in
`orchestrator.py`), so every inference request serialized through one machine.
Two machines are available, both running the same model with identical
settings. Requests should distribute across whatever machines are up.

## Core design decision: health is a snapshot at query start

To avoid the deadlock class that mid-query rebalancing introduces (traced and
rejected — see "Rejected: mid-query failover"), the router does **not**
rebalance mid-query:

- At **query start**, the router primes each configured endpoint (priming is
  the liveness check) and builds the pool from those that respond.
- **Global concurrency is derived from live capacity at start:**
  `up_endpoint_count × per_endpoint_cap`. Both machines up → 6; one down → 3.
  The query proceeds at whatever capacity is available and never refuses to
  start.
- During the query, endpoints are assumed stable. No mid-query mark-down, no
  re-evaluation.
- If an endpoint dies mid-query, its tasks fail as they do today. The always-on
  poller keeps health current so the **next** query's snapshot picks up the
  recovered endpoint automatically.

`delegate_tasks` is **untouched**: the global semaphore remains the single
blocking concurrency primitive, sized to live capacity at start.

## Deviations from the original design

### 1. Per-endpoint semaphores replaced with non-blocking least-loaded selection

**The original design deadlocks.** The spec called for a per-endpoint
`asyncio.Semaphore` acquired inside `_run_single_task`. That adds a second
blocking resource which — unlike the global semaphore — is never surrendered:

1. Orchestrator delegates N Searchers; each takes a global permit *and* a
   router permit, saturating the router.
2. Each Searcher calls `delegate_tasks`, which **releases its global permit**
   while awaiting children (orchestrator.py surrender/reclaim) but keeps its
   router permit.
3. Child Analyzers acquire global permits fine, then block on
   `router.acquire()`.
4. Every router permit is held by a parent awaiting those very children.
   **Hang.**

This is the same deadlock class the spec rejected for mid-query failover. The
spec's reasoning that snapshot-at-start removes it is wrong: the deadlock comes
from the parent-holds-slot-while-awaiting-children pattern, which is unrelated
to health changes. It cannot be fixed by surrendering the router permit either,
because `client.as_agent(...)` binds a sub-agent to a specific client at
construction time.

**As built:** the router is **selection-only**. Each endpoint keeps an
in-flight *counter*. `acquire()` picks the endpoint with the fewest in-flight
tasks (ties → config order), increments, yields its client, and decrements in a
`finally`. It **never blocks**. The global semaphore remains the sole blocking
admission primitive, sized at `up_count × per_endpoint_cap`.

**Consequence — `per_endpoint_cap` is a balance guarantee, not a hard local
ceiling.** While no parent is mid-delegation, total in-flight ≤ `N × cap` and
least-loaded assignment keeps each endpoint ≤ `cap`. During delegation a
parent's surrendered global permit isn't counted against the bound, so one
endpoint can briefly carry more than `cap`. Measured on a live 3-topic run:
**peak total in-flight 7 against a derived 6**, and **peak 4 on one endpoint
against cap 3**. This is a throughput wobble, not a correctness problem, and
the overshoot is bounded by delegation depth (Orchestrator → Searcher →
Analyzer = one surrendering layer).

The config key's name overstates what it does. Renaming it was judged not worth
the churn.

### 2. The TUI "Hello" primer was kept, not removed

The spec's cleanup section treats router priming and the TUI primer as the same
mechanism. They are not:

- **Router priming** is a bare chat completion — liveness check plus model
  warm-up. No tools, no session.
- **The TUI "Hello" turn** is a full agent turn whose purpose (per the code
  comment) is absorbing the malformed **tool-call stream** on a fresh
  *session*. It cannot be replaced by router priming, which never issues a tool
  call.

Removing the TUI primer would buy nothing and risk breaking the first real
query of every run. There is no double-priming problem because the two operate
at different layers. Live runs confirm the ordering: router messages first,
then the agent greeting.

If the malformation turns out to be per-*endpoint* rather than per-session, it
will surface as a first-task failure on the second machine; no evidence of that
so far.

### 3. `OPENAI_API_BASE` fallback removed entirely

The spec defined a precedence rule (array wins, env var as fallback). The
operator confirmed the env var is not used, so the fallback path and its test
surface were dropped. `openai_base_urls` is the only source of endpoint URLs.

### 4. `max_concurrent_tasks` removed, not aliased

Renamed to `per_endpoint_cap` with no backwards-compatibility alias. An
existing config with the old key now fails validation loudly rather than
silently running at the default cap of 1.

## Per-endpoint cap and global derivation

- **The config primitive is `per_endpoint_cap`** — the operator sets per-machine
  capacity, not a global total.
- Global concurrency = `up_endpoint_count × per_endpoint_cap`, computed at query
  start and used to size the global semaphore.
- **fast_test:** the overlay lowers `per_endpoint_cap` to 1. Derivation still
  applies, so two endpoints give global 2. fast-test keeps both endpoints.

## Endpoint selection

Least-loaded across the up endpoints. `_select_endpoint()` is synchronous and
pure: it returns the endpoint with the fewest in-flight tasks, ties breaking to
config order (which keeps single-endpoint behaviour identical to the pre-router
path).

Verified live — three Searchers plus their Analyzers alternated cleanly:
`.69`(1) → `.61`(1) → `.69`(2) → `.61`(2) → `.69`(3) → `.61`(3) → `.69`(4).

## Config

`config_template.yaml`:

```yaml
api:
  openai_base_urls:
    - http://localhost:8080/v1
  openai_model: local-model
settings:
  concurrency:
    # Concurrency limit for ONE endpoint (machine). Global concurrency is
    # derived at query start as: up_endpoint_count * per_endpoint_cap
    per_endpoint_cap: 3
```

One URL in the array = single endpoint, behaves exactly as today.

`config.py` normalises the list after the `fast_test` overlay: accepts a bare
string as a one-element list, strips whitespace, drops blanks and duplicates,
preserves order, and raises `ValueError` if the result is empty or if
`per_endpoint_cap` is not a positive integer.

## Per-endpoint priming (liveness check + warm-up)

- **At query start, the router primes every configured endpoint** that is up and
  not permanently down. Priming doubles as the liveness check.
- Priming is a bare completion (`"Reply with the single word: ready"`,
  `max_tokens=16`, 600s timeout so a cold LM Studio can load the model into
  VRAM). Reachability is governed by the client's 15s connect timeout, so an
  unreachable host fails in seconds rather than hanging.
- Each endpoint's result is surfaced **one message per endpoint** — a greeting
  on success, a failure notice on failure. Failure reasons are collapsed to a
  single line and capped at 160 characters with the exception type prefixed
  (an HTML error page from a non-LLM server on the port was previously
  flooding the log with ~18 lines and rendering blank in the TUI).
- Endpoints that prime successfully join the pool. Failed ones are excluded;
  the query proceeds on whatever primed.
- **Prime-once-per-endpoint-per-session.**
- A recovered endpoint is **primed before serving any real task** — `_mark_up`
  deliberately leaves `primed=False`.

## Health poller (always-on)

- One background task tied to the router singleton, started on first snapshot,
  cancelled at teardown. Polls every 5s.
- Probes with a cheap `GET /v1/models` (10s timeout, does not load the model).
- Backoff: **10s, 30s, then 60s**, up to **6 attempts** before marking an
  endpoint permanently down **for the session**. `_mark_up` does not clear
  `permanently_down` — a restart is required after that point. Total
  intervention window is ~4.5 minutes.
- A successful probe resets the backoff counter.
- Health flips (`_mark_up`, `_mark_probe_failed`) are **synchronous** — no
  `await` mid-flip — so they are atomic relative to other coroutines.
- The poller only updates state consumed by the **next** query's snapshot.

## Router lifecycle: singleton

Module-level singleton via `get_router()` / `aclose_router()`. Created once
lazily and reused across all `create_local_agent` calls, because
`create_local_agent` runs on every query and a per-call router would leak a
poll task each time. Health state persists across queries within a session.

### Teardown
`aclose()` cancels the poll task, logs a peak-concurrency summary, and closes
every endpoint's raw client. Idempotent. Called from:
- **TUI:** `on_unmount` on `BasicTuiAgent` (mirror of `on_mount`).
- **CLI:** the existing `finally` in `run_cli`, wrapped in try/except so a
  teardown failure cannot mask the real error.

## Logging

Log path: `~/.{APP_NAME}/logs/router.log`, **overridable via the
`DRA_ROUTER_LOG` environment variable**. The override exists because the logger
is built at module import time, so pytest was writing fake endpoints, fake
prime failures and fake peak summaries into the operator's live log (~51KB per
run) — and a hung pytest process held the file handle open, blocking log
rotation. Tests now set the variable before import and write to a temp file.

Every task acquisition and release is logged with the real endpoint URL:

```
ACQUIRE http://192.168.68.69:1234/v1 task='Research Qwen3-32B ...'
  inflight=1/3 total=1/6 served=1 peak_ep=1 peak_total=1
RELEASE http://192.168.68.69:1234/v1 task='Research Qwen3-32B ...'
  inflight=0/3 total=0/6
```

Per-task endpoint logging exists because the two machines have separate LM
Studio logs; without it a bad figure in a report cannot be traced to a machine.
`peak_summary()` is logged at teardown.

## Prompt-injected concurrency

`max_concurrency` injected into agent prompts reflects the **derived global
concurrency for the current query** (6 when both up, 3 when one down). All
three injection sites read `router.current_concurrency()`. Per-endpoint cap is
an internal router concern the agents never see.

## Implementation

### New file: `engine/router.py`
- `_EndpointState` per endpoint: `raw` (AsyncOpenAI), `client`
  (OpenAIChatCompletionClient), `inflight`, `peak_inflight`, `served`, `up`,
  `primed`, `fail_count`, `permanently_down`, `next_probe_at`.
- `snapshot_and_prime(notify=None)` → `(up_urls, derived_concurrency)`.
- `orchestrator_client()` — the first snapshot endpoint's client.
- `acquire(task_name)` — non-blocking async context manager (see Deviation 1).
- `_select_endpoint()` — synchronous least-loaded selection.
- `inflight_snapshot()`, `peak_summary()` — diagnostics.
- Poller, `aclose()`, config parsing, logging.

### Changed: `orchestrator.py`
- `_build_client` **deleted**; replaced by the router singleton.
- `create_local_agent` is now **async** and takes a `notify` callable. It takes
  the snapshot and primes at the top, then sizes the global semaphore from
  `router.current_concurrency()`.
- **The orchestrator agent is pinned to one endpoint for the whole query.**
  `client.as_agent(...)` binds a client at construction time and the
  orchestrator agent is built once per query, so it cannot route dynamically.
  It is a single serial stream, so this is harmless — but it means orchestrator
  load, including report synthesis, always lands on one machine. Distribution
  happens across sub-agents only.
- `_run_single_task` keeps `async with sem:` as the outer blocking gate. Inside
  it, sub-agent construction *and* its entire run are wrapped in
  `async with router.acquire(task_name=...) as _task_client:`. The quota and
  contextvar `finally` stays outside the acquire block.
- **`delegate_tasks` is NOT modified.**

**Context-passing requirement (honoured):** the `async for update in stream`
loop stays exactly where it is, inside the same context, with no manual
iteration. Only its indentation changed. This is the region of the prior
`agent_framework` 1.11.0 streaming-telemetry contextvar bug.

### Changed: `tui.py`
- All four `create_local_agent` call sites `await`ed.
- TUI notify callback mounts priming messages as system bubbles;
  CLI notify callback writes them to stdout (`[Router] ...`).
- Both banners display the joined URL list.
- `on_unmount` added to `BasicTuiAgent`; `aclose_router()` added to `run_cli`'s
  existing `finally`.
- The `on_mount` "Hello" primer is **retained** (see Deviation 2).

## Rejected: mid-query failover

An earlier design marked endpoints down mid-query and rebalanced live. Tracing
this against the surrender/reclaim in `delegate_tasks` showed a deadlock: a
delegating task holds its router slot across its `delegate_tasks` gather while
awaiting children; all slots can be held by awaiting parents, leaving child
Analyzers parked forever. The snapshot-at-start model was chosen instead.

**Note:** the same trace applies to the spec's own per-endpoint semaphore, which
is why it was replaced (Deviation 1). Snapshot-at-start removes the
*rebalancing* problem but not the parent-holds-slot problem.

## Unit tests

`tests/test_router.py` — **10 tests, all passing** (~1.3s). All mocked: no
network, no live endpoint, no agent framework runs. Every potentially-blocking
await is wrapped in `asyncio.wait_for` so a bug surfaces as a timeout failure
rather than a hung run.

| # | Test | Covers |
|---|------|--------|
| 1 | `TestInflightAccountingBalances` | 8 concurrent acquires complete; in-flight returns to 0; served totals correct |
| 2 | `TestInflightNoDriftOverRounds` | 10 rounds × 6 concurrent; zero drift after every round; catches a leaked increment |
| 3 | `TestLeastLoadedBalance` | 12 overlapping acquires spread across both endpoints; served counts differ by ≤2 |
| 4 | `TestSnapshotDerivesConcurrency` | both up → `2 × cap`; one prime fails → `1 × cap`, only the survivor pooled |
| 5 | `TestSingleEndpointEquivalence` | one-URL array → 1 url, `1 × cap`, `orchestrator_client()` identity; empty snapshot raises |
| 6 | `TestBackoffScheduleAndPermanentDown` | backoff follows `_BACKOFF`; `_MAX_FAILS` → permanently down; `_mark_up` resets and the schedule restarts |
| 7 | `TestMarkUpDoesNotSetPrimed` | a recovered endpoint must be re-primed before use |
| 8 | `TestACloseCancelsPollerAndIsIdempotent` | poll task cancelled, `_poll_task` cleared, second call safe, module singleton reset |
| 9 | `TestPrimeOnceAndSurfacedThenExcluded` | 2 messages surfaced; second snapshot re-primes nothing; failure excludes; all-fail raises |
| 10 | `TestSelectEndpointIsSynchronousAndNonBlocking` | picks least-loaded, stable tie-break, not a coroutine, never blocks under saturation, raises on empty snapshot |

**Changed from the original test plan.** The spec's tests 1–3 and 11 targeted
blocking semaphore semantics (`_acquire_first_available`, permit leaks, hard
caps) which no longer exist. They were replaced with counter-accounting,
drift, balance and non-blocking-selection tests. The spec's env-var precedence
case was dropped with the fallback (Deviation 3).

Not covered by unit tests: the `agent_framework` streaming/contextvar
interaction, which only surfaces against a live endpoint.

## Live validation — results

All four rungs completed against two real machines
(`192.168.68.69`, `192.168.68.61`, both serving `qwen/qwen3.5-9b`).

| Rung | Result |
|------|--------|
| **1. Single-URL array** | Banner correct, one priming message, "Hello" after it, no traceback. Snapshot: `1 endpoint(s), global concurrency = 3` — identical to pre-router behaviour. |
| **2. Two endpoints** | Two priming messages, both banners correct. Snapshot: `2 endpoint(s), global concurrency = 6`. Work spread across both machines (7 tasks on `.69`, 4 on `.61`). Least-loaded alternation confirmed. No `Task failed with exception` — the contextvar regression did **not** resurface. |
| **3. Deliberately-dead endpoint** | Third URL at `127.0.0.1:9999` primed-failed with a clear reason, was excluded, app did not crash, greeting still arrived. Snapshot still `2 endpoint(s), global concurrency = 6` — the dead endpoint contributed no capacity. |
| **4. Poller recovery** | `.61`'s LM Studio stopped → startup snapshot `1 endpoint(s), global concurrency = 3` with `APIConnectionError: Connection error.` Server restarted → **34 seconds later** `.61` primed OK and the next snapshot read `2 endpoint(s), global concurrency = 6`. Full path exercised: probe fail → down → probe succeed → `_mark_up` → re-primed at next snapshot → included. |

**Peak concurrency measured:** total 7 (against derived 6), per-endpoint 4 on
`.69` and 3 on `.61` (against cap 3). Explained by the surrender/reclaim
overshoot in Deviation 1.

### Not yet validated

- **No completed end-to-end research run.** Two attempts were cut short — one
  by the pre-existing Reviewer loop, one by quitting mid-flight. Timing has
  only a single-endpoint-era baseline (7m28s to report-written on a 3-topic
  query) with no clean two-endpoint comparison.
- **The standard 7-model query has not been run.** Report-quality parity
  against a single-endpoint baseline is therefore unconfirmed.
- **No long-run capacity check.** In-flight counters returned cleanly to zero
  over a 30-minute session and 10 test rounds, but not over a multi-hour run.

## Known issues surfaced during this work (not router bugs)

- **Reviewer loop.** On a live run the Reviewer made **38 `grep_workspace_file`
  calls**, 25 of them two patterns alternating (`\]http` → always 0 matches,
  `\]\(https://` → always the same 3 matches) against an unchanged file.
  Because consecutive calls are never *identical*, the threshold-based repeat
  breaker never fires. This is the alternating-pair evasion already on the
  backlog, and it is independent of the router (it ran on the machine that was
  always in use). Worth noting the repeats are also **cacheable** — the same
  grep on an unchanged file is detectable without relying on consecutiveness.

## Out of scope

Mid-query failover / rebalancing, re-dispatch of a failed in-flight task,
round-robin/affinity routing, per-endpoint differing model settings.
