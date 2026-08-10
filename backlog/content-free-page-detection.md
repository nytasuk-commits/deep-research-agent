# Detect content-free pages structurally (no matchable error text)

**Status:** Open
**Type:** Backlog (enhancement)
**Priority:** Medium — the marker-based fixes cover 29 of 31 audited junk classes; this covers the residual 6 files
**Depends on:** none
**Blocks:** none

## Problem

Six junk pages from the 2026-08-08 audit cannot be caught by any string marker, because they contain no error text at all. They are successful HTTP 200 responses whose real content never rendered:

| File | Size | What was saved |
|---|---|---|
| `localai_deepseek_r1_distill_70b_deepdive.md` | 690 | YouTube footer links only (About/Press/Copyright/Terms), plus "© 2026 Google LLC" |
| `minisforum_deg1_youtube.md` | 690 | byte-identical to the above, different video URL |
| `nvidia_qwen3_next_80b_modelcard.md` | 903 | NVIDIA NIM top nav + legal footer; model card body absent |
| `nvidia_nim_qwen3_next_modelcard.md` | 903 | byte-identical to the above, same URL fetched under a second filename |
| `basedagi_deepseek_r1_distill_70b_benchmarks.md` | 974 | site nav + footer, body is the single word "loading…" |
| `qwen3_next_80b_llmfit.md` | 640 | site nav, body is "Loading model...", plus a schema.org JSON blob describing the *website* (not the model) |

All six pass the 200-char floor and match no `_block_markers` entry. Two sub-patterns:

- **Nav-only shells** (4 files): content is almost entirely markdown link syntax. No sentences.
- **JS loading shells** (2 files): a "loading" placeholder where the data should be. `qwen3_next_80b_llmfit.md` is the more dangerous of the two, because the preserved embedded JSON (feature `4b97706`, added so Shopify prices survive markitdown) makes an empty page look substantive — an automated audit misread it as real content for exactly this reason.

## Why markers cannot fix this

There is no distinctive phrase to match. A YouTube footer is legitimate text that also appears on real YouTube pages. Adding "loading" as a marker would reject any page whose prose contains the word.

## Candidate approaches (undecided)

1. **Link-density / prose ratio.** Reject when the proportion of characters inside markdown link syntax exceeds a threshold and no sentence-like run of prose exists. Catches all 4 nav shells and probably both loading shells. Risk: legitimately terse link-heavy pages (index pages, directory listings) that the Searcher may want.
2. **Sentence-count floor.** Require at least N sentences (a run of words ending in `.`/`?`/`!` outside a link). Simple, and orthogonal to length. Risk: spec tables and pure-data pages are legitimately sentence-free — note `g4_meromero_26b_a4b_gguf_model.md` (683 bytes) was judged REAL despite being almost entirely label/value pairs, so a naive sentence floor would have rejected it.
3. **"Loading" placeholder as body.** Narrow rule: reject if, after stripping nav/links, the remaining prose is under ~50 chars AND contains "loading". Targets the 2 JS shells specifically with low false-positive risk.
4. **Discount embedded JSON when measuring content.** The preserved `<script>` JSON should not count toward the length floor or the substantive-content measure, since site-metadata JSON is boilerplate. Independent of the above and worth doing regardless.

Approach 3 + 4 are low-risk and narrow. Approach 1 or 2 is the general fix but needs false-positive testing against the ~3540 existing workspace .md files before adoption — the audit showed real content can be terse and label-heavy.

## Related

- `bugs/long-junk-pages-pass-filters.md` — the case this splits off from
- `bugs/done/junk-fetches-saved-as-sources.md` — the short-junk floor (closed)
- `src/tools/web.py` — `_block_markers`, `_MIN_CONTENT_CHARS`, the 20000-char marker ceiling
