# truststore Missing from pyproject.toml

**Status:** Done
**Type:** Backlog
**Source:** Clean venv rebuild failure

## Resolution
Added truststore to pyproject.toml dependencies; committed.

## Summary
truststore not declared as a dependency; a clean venv rebuild fails without it.

## Detail
During a clean virtual environment rebuild, the system failed due to missing truststore dependency. This package is being imported but not listed in pyproject.toml dependencies.

## Action needed
1. Add truststore to pyproject.toml dependencies
2. Audit for other undeclared dependencies

## Related
- pyproject.toml
