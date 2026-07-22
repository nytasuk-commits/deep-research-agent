# TUI Renders Tool Calls in Raw XML Dialect

**Status:** Open
**Type:** Backlog
**Source:** Observed in run

## Summary
Cosmetic but confusing display of the model's tool-call output.

## Detail
The terminal UI shows raw XML dialect used by the model for tool calls (e.g., `<parameter=...>` tags) rather than a clean, parsed representation. This is confusing for users monitoring the run and doesn't add diagnostic value.

## Suspected fix
Parse and format tool call display in the TUI to show intent/action names rather than raw XML.

## Related
- src/engine/tui.py
