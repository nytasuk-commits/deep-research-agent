# Synthesis Salience/Variance

**Status:** Open
**Type:** Backlog
**Source:** Spec item 8

## Summary
Report quality swings run-to-run; levers include lower synthesis temperature or run-N-keep-best.

## Detail
The synthesis stage produces inconsistent output quality across runs. This variance is undesirable for production use as it makes results unpredictable and reduces reliability.

Possible mitigation strategies:
1. **Lower synthesis temperature** - reduces creativity, increases consistency
2. **Run-N-keep-best** - run multiple times and select the highest-quality output
3. **Temperature + top_p tuning** - balance coherence with coverage

## Related
- Spec item 8
