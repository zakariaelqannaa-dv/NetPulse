# Security Policy

NetPulse runs locally, needs no administrator rights for normal diagnosis, and
never uploads anything. Even so, it launches Windows tools, reads system state,
can apply reversible network changes, and writes report files that contain
network identifiers — so security matters.

---

## Supported versions

| Version | Supported |
| ------- | --------- |
| 1.0.x   | Yes       |

Only the latest 1.0.x release is supported with security fixes. Please test
against the most recent release before reporting an issue.

---

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Report it privately by opening a draft security advisory on the repository
(Security → Advisories → "Report a vulnerability"), or by e-mail to the
maintainer listed on the repository profile.

Please include:

- the affected version,
- a clear description of the problem,
- steps to reproduce, with a minimal example where possible,
- the impact you believe it has,
- any suggested fix.

You can expect an acknowledgement within a few days. Please allow reasonable time
for a fix before public disclosure.

---

## What is in scope

We are particularly interested in:

- **Command injection.** Any path where user-supplied input can reach a shell, a
  PowerShell command line, or a subprocess in a way that is not an explicit
  argument array with `shell=False`.
- **Path traversal.** Any path where a file name or path can escape the intended
  directory (for example during report export or snapshot handling).
- **Unsafe privilege use.** Any code path that elevates or applies a system-level
  change without explicit user confirmation, or that writes to a system-wide
  setting outside the documented, reversible actions.
- **Redaction failures.** Any case where a field selected for redaction still
  appears in an exported report, including inside generated sentences.

Report output correctness issues (for example a wrong statistic) are also welcome
as normal bug reports if they do not have a security impact.

---

## What is out of scope

- Vulnerabilities in Windows itself, in PySide6, in `psutil`, in `dnspython`, or
  in other dependencies — please report those upstream.
- The accuracy or interpretation of diagnostic results. NetPulse reports what it
  measured and says what it cannot measure; it does not guarantee a diagnosis.
- Problems that require an attacker who already has administrator rights or
  physical access to the machine.
- Missing hardening that has no demonstrable impact (for example the absence of a
  feature that NetPulse explicitly does not implement).

---

## Privacy and data-handling guarantees

These are deliberate design properties, not configuration options:

- **NetPulse never uploads data.** No report, measurement or telemetry is sent
  anywhere. There is no analytics, no account and no background monitoring.
- **NetPulse never runs a network service.** It opens no listening socket and
  installs no background service.
- **No auto-start.** NetPulse does not add itself to Windows startup.
- **All local state** lives under `%LOCALAPPDATA%\NetPulse` and can be deleted at
  any time; the Diagnostics History page offers a Clear History action.
- **Exported reports contain network identifiers** and can be fully or partially
  redacted before the file is written.

A vulnerability that contradicts any of the statements above (for example, code
that transmits data off the machine) is considered in scope and should be
reported privately.
