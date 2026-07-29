# Repository guidance

## Before making changes

- Read `README.md` and the relevant documents in `docs/`.
- Inspect existing code and tests.
- Keep changes limited to the assigned task.

## Public repository

- Treat every committed file as publicly visible.
- Never commit real reservation data, browser profiles, cookies, authentication state,
  exports, production screenshots, production HTML, traces, or private logs.
- Use only invented data in tests and documentation.

## Safety

- Termino access is strictly read-only.
- Never create, edit, copy, cancel, or delete reservations.
- Never invoke actions labelled `Upravit`, `Odstranit`, or `Zkopírovat rezervaci`.

## Browser automation

- Use Playwright DOM locators; prefer accessible roles, labels, and stable text.
- Do not use OCR, image recognition, or fixed coordinates for extraction.
- The reservation detail has its own internal scroll container.
- Centralize selectors when browser automation is introduced.
- One reservation failure must not stop the entire export.

See `docs/SPEC.md`, `docs/SECURITY.md`, and `docs/ROADMAP.md` for details.

## Quality

For changes to Python code, run:

```text
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy src
```

- Add or update tests for behavioral changes.
- Do not weaken checks merely to hide failures.
- Update documentation when behavior or setup changes.
- Report which verification commands were actually run.
