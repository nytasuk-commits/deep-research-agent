# Don't charge web_calls quota for rejected fetches

**Status:** Open
**Type:** Backlog
**Source:** Design discussion 2026-07-20, arising from the junk-fetch length-rejection fix.

## Summary
A fetch that is rejected (block-marker match, too-short/junk content, image-only page) still consumes a web_calls quota unit, because @with_quota increments the counter at the start of the call before the rejection logic runs. Consider only charging quota for fetches that actually save usable content.

## Detail
fetch_url_to_workspace is decorated with @with_quota; check_quota increments web_calls.used before the fetch/strip/length checks execute. So rejected junk still costs a call. On a full budget (100) this is negligible, but under the fast-test profile (web_calls: 12) a junk-heavy query can burn the budget on rejected fetches before enough real sources are gathered.

## Trade-off / caution
Not charging for rejected fetches reintroduces a junk-retry-loop risk — a model hitting a string of bad URLs could retry endlessly if each rejection is "free". Any implementation must pair with the loop-breaker (already in place, _check_repeat in src/tools/core.py) to prevent unbounded retrying. Charging rejected fetches is currently a deliberate safety feature, so this change is an optimisation, not a bug fix — weigh carefully.

## Possible approach
Move the quota increment for this tool so it fires only on a successful save, rather than at call entry — which means decoupling fetch_url_to_workspace from the standard @with_quota entry-increment and incrementing manually after the save succeeds.

## Progress
None yet — awaiting priority review and design approval.

## Related
- src/tools/core.py (with_quota, check_quota, _check_repeat)
- src/tools/web.py (fetch_url_to_workspace)
- bugs/junk-fetches-saved-as-sources.md
- backlog/fast-test-config-profile.md
