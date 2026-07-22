# High FETCH TIMEOUT frequency may be starving coverage

**Observed:** In run session_d0d41640, the 60s hard fetch ceiling (commit a958662) fired 6 times out of 21 fetch calls — roughly a third of fetches cut off on slow/trickling servers.

**Assessment:** The ceiling itself is working as designed (defeating byte-trickle timeout resets). The concern is volume: if a third of fetches are being cut, coverage and run time both suffer.

**Fix direction (tuning, not a bug):** Watch whether frequent timeouts correlate with thin reports. Levers if it becomes a problem: tune the ceiling value, add a short retry against a different source when a fetch times out, or prefer sources known to respond quickly. Do NOT lower the ceiling in a way that lets byte-trickle servers hang again.

**Priority:** Low. Monitor; act only if timeouts are visibly degrading report quality.

## Update — timeouts are vendor storefronts, not slow servers (session_427804ec)

In a fast-test run, all 5 FETCH TIMEOUTs were manufacturer storefronts:
- https://www.bee-link.com/products/beelink-gtr9-pro-amd-ryzen-ai-max-395 (×2)
- https://www.bee-link.com/collections/gt-series
- https://store.minisforum.com/products/minisforum-ms-a2-workstation
- https://www.minisforum.com/products/minisforum-ms-a2

These URLs load fine in Chrome locally but hang the httpx fetch client to the 60s
ceiling. Pattern: Shopify-style vendor storefronts with bot protection that detect
a non-browser client (TLS fingerprint / missing browser headers) and hold the
connection open rather than returning a quick block — so the fetch trickles to the
ceiling instead of failing fast.

Impact is compounding: the Searcher is instructed to prefer the manufacturer store
FIRST for pricing, so every price query wastes ~60s on each vendor URL and then
falls back to reviews/resellers — which is also why prices keep coming from
secondary sources rather than the official store.

Fix directions to consider (NOT the ceiling — the ceiling is working):
- Detect and short-circuit known-unfetchable vendor domains fast (fail in ~5s, not 60s).
- Or improve the fetch client for these (browser-like headers, HTTP/2, or a
  browser-emulating fetch path) so vendor pages actually return.
- Ties to backlog/dedup-remember-blocked-urls.md (remember these so they aren't
  retried within a run — note bee-link was hit twice this run).
