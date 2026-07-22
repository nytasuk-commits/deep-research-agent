# Dedup should remember BLOCKED/failed URLs, not just successful fetches

**Observed:** In run session_d0d41640, `https://www.bee-link.com/products/beelink-gtr9-pro-amd-ryzen-ai-max-395` was fetched twice in one run. The first fetch was BLOCKED (interstitial marker caught it). The second identical fetch was NOT recognised as a repeat, so a fetch call was wasted.

**Cause:** URL dedup (in `_fetched_urls`) only records a URL AFTER a successful save. BLOCKED / TIMEOUT / junk-rejected fetches return early before the "record successful fetch" step, so the URL never enters the registry and can be re-fetched any number of times within the same run.

**Fix direction:** Also record URLs that returned BLOCKED (and possibly FETCH TIMEOUT / junk-reject) in a per-run "do-not-retry" set, and short-circuit repeat attempts with a message telling the agent the URL already failed this run and not to retry it. Keep it per-run and memory-bounded like the existing dedup registries.

**Priority:** Low. Efficiency, not correctness — reliably-blocked domains (vendor stores) waste one fetch each per run.
