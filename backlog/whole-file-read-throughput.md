# Whole-File Read Throughput

**Status:** Open
**Type:** Backlog
**Source:** Spec item 7

## Summary
Analyzer should grep-first by default rather than reading whole files.

## Detail
Current analyzer behavior reads entire files before searching for patterns. This is inefficient because:
1. Many files are large and mostly irrelevant
2. Pattern matching could filter content early
3. Memory usage is higher than necessary

Grep-first approach would:
1. Scan for relevant patterns first
2. Only read full file content when a match is found
3. Reduce both time and memory overhead

**Observed evidence (8-model run, 2026-07-19):** Total wall-clock time was ~6h10m (first source file written 11:37, final report 17:47). Source files were read whole into Analyzer prompts, including several very large ones (e.g. strix_halo_guide.md ~250KB, gemma3_report_143022.md ~181KB, qwen3_arxiv_technical_report.md ~154KB). With one local model serving many concurrent Analyzer calls, these large whole-file reads are a primary driver of runtime. Grep-first targeted reads would cut per-Analyzer prompt size substantially and are likely the single biggest runtime lever.

## Refinement

Investigation on 2026-07-20 (using the 6h10m 8-model run's workspace) found the throughput problem has THREE distinct costs, not one:

1. **Many distinct small greps (serial round-trips).** The loop-breaker handles identical-consecutive greps, but NOT sequences of different narrow greps (e.g. price, then RAM, then DDR5, then capacity separately). Each is a serial model round-trip; this was a large share of the 424 greps in that run. **Fix:** grep with a focused combined pattern to locate relevant sections, rather than iterating keyword-by-keyword.

2. **Large-file slicing — NOT actually a problem; leave the 400-line cap as-is.** The largest source (strix_halo_guide.md) is ~2,000 lines, i.e. only ~5 reads at the 400-line cap. 400 is a reasonable per-read ceiling for a targeted section; lowering it would force more reads (reintroducing cost #1), raising it risks dumping most of a big file into the prompt. The real fix is size-adaptive strategy, not cap tuning: small file (under ~400 lines) → read whole in one call; large file → grep-to-locate then read a targeted ~400-line window around the best match. Cap returned match volume so a broad grep on a huge file can't dump excessive context.

3. **Repeated fetching of the same source** — real but smaller than first thought; content mostly differs. The same guide was saved ~29 times under different filenames (strix_halo_guide.md, _github.md, _v2, _kimi_k2, _qwen, _readme, etc.). Initial assumption was these were identical re-fetches (pure waste). MD5 hashing on 2026-07-20 corrected this: content is mostly unique across the copies (~20 distinct hashes), with only a few small identical clusters (one group of 4, one of 3, several pairs). So two separate issues: (a) byte-identical duplicates (the clusters) — genuine wasted re-fetches, fixable by dedup (skip a fetch whose URL or content already exists this run); modest saving. (b) search overlap — 8 tasks independently converging on and fetching the same popular source ~20 times even when content differs slightly; this is the larger inefficiency and is a search/planning problem (avoid dispatching overlapping fetches of the same source), not a byte-dedup problem.

**Priority among these:** #1 (grep strategy) and #3b (search overlap) are the larger levers; #3a (byte-dedup) is a modest, easy win; #2 needs no cap change. Note the earlier "biggest single lever = dedup" claim was based on a miscount — content across the ~29 copies is mostly distinct, so pure dedup saves less than first assumed.

## Related
- Spec item 7
