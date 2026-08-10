# Long anti-bot / interstitial pages pass both length and block-marker filters

**Status:** Open — general case confirmed by 2026-08-08 audit; marker-catchable subset now fixed
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

### Update 2026-08-08: general case confirmed, and two undocumented gaps found

An audit of 34 sub-1KB fetched sources (read in full, not sampled) found 31 junk, in eight distinct classes. The deferred "future bot-wall with unrecognised text" is not hypothetical — it was already happening at scale.

Two mechanisms were missed by this file's original analysis:

1. **The marker check was case-sensitive.** 19 of the 31 junk files were rejection pages whose text differed from an existing marker only by capitalisation: Akamai/EdgeSuite emits "# Access Denied" (capital D) against a marker reading "Access denied"; TechPowerUp emits "# 403 - Access Denied". Fixed by matching case-insensitively — no new strings required for those 19.
2. **The marker check only runs on pages under 20000 chars.** This ceiling is undocumented in this file and narrows the "long junk" case further than the title implies: a genuinely long bot wall never reaches the marker check at all. Not exercised by any file in this audit (all were under 1KB), so it remains untested rather than confirmed.

A further 10 files were fixed by adding eight markers for soft-404s served with HTTP 200 (GitHub Pages ×2 templates, LiteSpeed, RePEc/IDEAS, Effloow), a TechPowerUp CAPTCHA wall, an idealo error page and an Oracle outage page. A bare "404" marker was deliberately rejected as too broad. "Something has gone wrong" was narrowed to "Sorry! Something has gone wrong" after it matched legitimate troubleshooting prose in testing — false positives are costly here because a BLOCKED result instructs the agent never to retry the URL.

The residual 6 files have no matchable text and are split out into `backlog/content-free-page-detection.md`. The low-substantive-prose-ratio idea this file proposed is still the right direction for them, and the audit supplies the false-positive counterexample it needs to be tested against: `g4_meromero_26b_a4b_gguf_model.md` is genuine content at 683 bytes with almost no prose, only label/value pairs.

Separately observed, not junk-related: the same Tesco store URL was fetched four times across four runs and the same LoopNet and NVIDIA NIM URLs twice each, every time returning the same rejection page. Dedup is per-run, so a known-blocked URL is re-paid for on every subsequent run — see `backlog/dedup-remember-blocked-urls.md`.

## Related
- src/tools/web.py (_block_markers, junk-length gate)
- Searcher prompt source-selection guidance in src/prompts.py
- bugs/junk-fetches-saved-as-sources.md (sibling — short-junk case)
- `backlog/content-free-page-detection.md` (residual markerless cases split out 2026-08-08)
