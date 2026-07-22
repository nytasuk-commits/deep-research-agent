# Long anti-bot / interstitial pages pass both length and block-marker filters

**Status:** Done (specific case) — general case deferred
**Type:** Bug
**Source:** Observed 2026-07-20 — amazon_gtr9_pro_us.md (amazon.com) saved as a source containing only anti-bot/interstitial chrome with no product data.

## Summary
A fetched page can be junk (bot wall, cookie/robot-check interstitial, pure navigation chrome) while being well over the 200-char length threshold AND not matching any string in _block_markers. It then gets saved as a real source and fed to the Analyzer.

## Detail
Important nuance: Amazon is inconsistent, not uniformly blocked. In the same session, the US fetch (amazon_gtr9_pro_us.md) returned anti-bot chrome, but the UK fetch (amazon_gtr9_pro_uk.md) returned a legitimate ~110KB product page with real "About this item"/"Buying options"/reviews content. So a blanket "avoid Amazon entirely" fix is too blunt — it would discard the good fetches too.

The length gate catches short junk; _block_markers catches known junk phrases; this is long junk whose marker text isn't listed. Adding one Amazon phrase is whack-a-mole (the spec warned against string-by-string marker maintenance), and per-region variants make it worse.

Suspected fix (needs design): favour detecting content-free pages by low substantive-text ratio (mostly navigation/boilerplate/links vs. real prose) rather than by domain-banning or marker strings — this rejects the bot-wall fetches while keeping legitimate product pages regardless of domain. Strengthening the Searcher's existing "prefer manufacturer store over marketplace" guidance may also reduce Amazon reliance, but must not hard-ban it given some Amazon fetches are genuinely useful.

## Resolution (2026-07-20)

The specific Amazon interstitial was fixed by adding its header phrase "Click the button below to continue shopping" to the existing `_block_markers` list in `src/tools/web.py` (commit for "Add Amazon 'continue shopping' interstitial to _block_markers"). Investigation corrected an earlier assumption: the US bot-wall was only 345 chars (not "long junk") — it barely cleared the 200-char threshold and its distinctive interstitial phrase makes it a clean `_block_markers` match, which is that list's intended purpose (not whack-a-mole). The UK fetch of the same product returned a legitimate ~110KB page, confirming Amazon is inconsistent rather than uniformly blocked, so a domain-ban was correctly avoided.

## Deferred (general case)

This marker fix only catches this known interstitial. A future bot-wall with unrecognised text would still pass. The general "detect content-free pages by low substantive-prose ratio" approach remains a possible enhancement if markerless bot-walls start appearing — but it carries false-positive risk on genuinely terse real listings (e.g. the 244-char eBay / 354-char Amazon listings that are real content), so it's deferred unless the need proves real.

## Related
- src/tools/web.py (_block_markers, junk-length gate)
- Searcher prompt source-selection guidance in src/prompts.py
- bugs/junk-fetches-saved-as-sources.md (sibling — short-junk case)
