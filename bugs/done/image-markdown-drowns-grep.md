# Image-Markdown Drowns Grep on Product Pages

**Status:** Done

## Resolution
Validated on 2026-07-20 fast-test run: 180 image references stripped from the Beelink product page, provenance note present, zero image markdown remaining, no Analyzer grep-flailing. Fix confirmed working.
**Type:** Bug
**Source:** Observed in run

## Summary
Analyzer greps on image-heavy pages return `![...](...png)` lines instead of specs, causing repeated identical greps.

## Detail
When the Analyzer processes product pages with many images, the grep patterns match markdown image syntax rather than actual specification content. This produces false positives that look like relevant matches but are just image references, leading to redundant analysis cycles as the system keeps finding "the same" content.

## Suspected fix
Strip image markdown before or during analysis to prevent `![...](...)` patterns from interfering with spec detection.

## Progress
Fix committed 2026-07-19 (commit 1751454): `_strip_image_markdown` in src/tools/web.py removes whole-line standalone image markdown from fetched pages before saving, collapses blank runs, and prepends a visible provenance note when images were stripped. NOT yet confirmed by a live run — remains open until a run shows the Analyzer greps finding specs instead of image noise on an image-heavy page.

## Related
- src/tools/web.py
- Analyzer flow
