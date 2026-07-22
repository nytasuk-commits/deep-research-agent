# High FETCH TIMEOUT frequency may be starving coverage

**Observed:** In run session_d0d41640, the 60s hard fetch ceiling (commit a958662) fired 6 times out of 21 fetch calls — roughly a third of fetches cut off on slow/trickling servers.

**Assessment:** The ceiling itself is working as designed (defeating byte-trickle timeout resets). The concern is volume: if a third of fetches are being cut, coverage and run time both suffer.

**Fix direction (tuning, not a bug):** Watch whether frequent timeouts correlate with thin reports. Levers if it becomes a problem: tune the ceiling value, add a short retry against a different source when a fetch times out, or prefer sources known to respond quickly. Do NOT lower the ceiling in a way that lets byte-trickle servers hang again.

**Priority:** Low. Monitor; act only if timeouts are visibly degrading report quality.
