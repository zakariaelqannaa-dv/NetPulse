# Contributing to NetPulse

Thanks for your interest in improving NetPulse. This document explains how to set
up a development environment, the conventions the project follows, and what a
good pull request looks like.

By participating you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

---

## Development environment

NetPulse targets **Windows 10/11** and **Python 3.12+**.

```powershell
git clone https://github.com/zakariaelqannaa-dv/NetPulse.git
cd NetPulse
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

Run the application:

```powershell
python -m app
```

Run the tests and the linter:

```powershell
python -m pytest -q
python -m ruff check .
```

The unit tests must stay **offline**: they must not require a live network
connection, and they must not touch the real user profile. Use the
`NETPULSE_DATA_DIR` environment variable to redirect on-disk state into a
temporary directory.

---

## Code style

- **Ruff** is the linter, configured in `pyproject.toml`.
- **Line length is 100 characters.**
- Target version is **py312**; use modern syntax where it improves clarity.
- Enabled rule families: `E`, `F`, `W`, `I`, `B`, `UP`, `S`, `C4`, `SIM`.
- `S603`/`S607` are intentionally ignored because NetPulse always launches
  subprocesses with an explicit argument list and `shell=False`, and locates
  Windows tools by name on the PATH.
- `S101`, `S105` and `S106` are ignored inside `tests/` only.

Run the linter before every commit:

```powershell
python -m ruff check .
```

---

## Architecture rule: keep diagnostic logic GUI-free

**Diagnostic logic must stay free of any GUI dependency and must be unit
testable.** Nothing under `app/core/`, `app/network/`, `app/optimization/` or
`app/reporting/` may import PySide6 or otherwise depend on a display.

In practice this means:

- Parsing and calculations are **pure functions** that take text/data in and
  return models out, so they can be tested directly.
- Anything that shells out or opens a socket takes its collaborator through an
  injectable parameter (see `EngineDependencies` in `app/core/engine.py` and
  `CommandExecutor` in `app/optimization/state.py`) so tests can substitute a
  deterministic fake.
- The GUI reads the models and renders them; it does not compute results.

---

## Adding a new diagnosis rule

The diagnosis engine lives in `app/core/diagnosis.py`. Rules are plain functions
with the signature:

```python
def rule_example(report: DiagnosticReport, th: dict[str, float]) -> list[Diagnosis]:
    ...
```

To add a rule:

1. Write a function that inspects a `DiagnosticReport` and returns a list of
   `Diagnosis` objects (import them from `app.core.models`).
2. For every `Diagnosis`, provide all of the following:
   - `rule_id` — a short stable identifier (for example `WAN-008`).
   - `finding` — the conclusion in one line.
   - `evidence` — the actual measured values, not a summary.
   - `confidence` — `Confidence.LOW`, `MEDIUM` or `HIGH`, chosen honestly.
   - `severity` — `Severity.GOOD`, `INFO`, `WARNING` or `CRITICAL`.
   - `meaning` — what the finding may indicate.
   - `recommendation` — the recommended next action.
   - `cannot_verify` — what NetPulse cannot determine here.
   - `category` — the functional group (for example `wan`, `wifi`, `dns`).
3. Register the function in the `RULES` tuple. The order matters only for
   readability; the overall status is computed from the worst severity.
4. Add unit tests that exercise the new rule with representative reports,
   including the "no data" case.

**Never** write a rule that claims NetPulse can fix ISP congestion, radio
signal, damaged cables, router hardware or external routing. If a symptom is
beyond the router, say so and explain which party (router, ISP, physical link)
would need to investigate.

---

## Adding a new optimization action

Optimization actions live in `app/optimization/actions.py` (definition) and
`app/optimization/state.py` (read-only checks). Every action must:

1. Be declared as a `NetworkAction` with a clear `title`, `summary` and `why`.
2. List its **trade-offs** explicitly, so the user understands the cost.
3. Set an honest `risk` level (`RISK_LOW`, `RISK_MEDIUM`, `RISK_HIGH`),
   `requires_admin` and, if applicable, `requires_reboot`/`is_destructive`.
4. Write a **snapshot** of the previous value *before* the change, with an
   `undo_args` or `undo_script` that can put it back.
5. Add an apply branch in `apply_action` and a matching entry in
   `preview_command` so the exact command can be shown before confirmation.
6. Never disable Firewall, Defender, IPv6 or security features.
7. Never force link speed, duplex, checksum offload or arbitrary MTU values.
8. Never run `netsh winsock reset`, `netsh int ip reset` or adapter resets
   automatically — they stay advanced, separately confirmed, destructive actions.
9. Add unit tests using a fake `CommandExecutor` (no real system changes).

---

## Adding a new report format

Report writers live in `app/reporting/`. The JSON report is the canonical,
lossless representation; the TXT and HTML writers consume the same dictionary, so
a new format should do the same.

1. Create `app/reporting/<format>_report.py` exposing a `render_<format>(report_data: dict) -> str`
   function that performs no I/O and touches no network.
2. Reuse the presentation helpers in `app/reporting/formatting.py` so wording and
   number formatting stay consistent.
3. Extend `ReportFormat`, `FORMAT_EXTENSIONS` and `FORMAT_LABELS` in
   `app/reporting/exporter.py`, and add the branch to `render_report`.
4. Make sure redaction still works: the new writer must not bypass
   `redact_report_data`.
5. Add tests for the new renderer.

---

## Required tests

Every change should come with tests. In particular:

- New parsing or calculation logic needs direct unit tests, including edge cases
  (empty input, localised input, missing fields).
- New diagnosis rules need tests for the finding, evidence and confidence.
- New report output needs a test that asserts the essential sections are present.
- Redaction changes need tests that confirm sensitive values no longer appear.
- Nothing in the test suite may reach the network or modify the real machine.

---

## Commit messages

Write clear, imperative, present-tense messages. A conventional-commit style
prefix is preferred:

```
feat(diagnosis): add rule for repeated gateway loss
fix(reporting): keep jitter line readable in the text report
docs(user-guide): clarify why a * hop is not proof of loss
test(network): cover localised tracert output
chore(ci): run Ruff before pytest on Windows
```

Use `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci` or `chore`.
Keep the subject under ~72 characters and explain the *why* in the body when it
is not obvious.

---

## Pull request checklist

Before opening a pull request, confirm that:

- [ ] `python -m ruff check .` passes with no errors.
- [ ] `python -m pytest -q` passes.
- [ ] New or updated tests were added for the change.
- [ ] No GUI dependency was added to `app/core`, `app/network`,
      `app/optimization` or `app/reporting`.
- [ ] No security feature was disabled or weakened (Firewall, Defender, IPv6,
      validation, redaction).
- [ ] Any user-visible change is documented (README and/or `docs/`).
- [ ] The documentation was updated where behaviour or wording changed.

Please keep pull requests focused. One logical change per pull request is easier
to review and safer to merge.
