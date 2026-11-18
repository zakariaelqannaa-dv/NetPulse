# NetPulse

[![CI](https://github.com/zakariaelqannaa-dv/NetPulse/actions/workflows/ci.yml/badge.svg)](https://github.com/zakariaelqannaa-dv/NetPulse/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Code style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Windows 10/11](https://img.shields.io/badge/Windows-10%2F11-blue.svg)](https://www.microsoft.com/windows)

**Tags:** `windows` `network` `diagnostics` `latency` `jitter` `packet-loss` `dns` `wifi` `ethernet` `troubleshooting`

NetPulse is an open-source Windows 10/11 desktop application that **diagnoses**
internet connection problems — high ping, unstable latency, jitter, packet loss,
DNS issues, Wi-Fi problems, Ethernet negotiation issues and possible ISP/WAN
instability — and explains the results in plain language.

---

## What NetPulse is

NetPulse is a **diagnostic and safe-configuration tool**. It measures the local
network, router reachability, internet latency, jitter, packet loss, DNS
resolution and route behaviour, then reports transparent, rule-based findings.
Every finding contains the measured **evidence**, a **confidence** level, what it
may **mean**, a **recommended next action**, and an explicit statement of **what
NetPulse cannot verify**.

NetPulse aims to answer one question honestly: *is the problem inside my PC,
between my PC and the router, or beyond the router?*

## What NetPulse is not

NetPulse is **not an "internet booster"** and does not promise a one-click fix.

- It never claims to fix ISP congestion, weak radio signal, damaged cables, bad
  router hardware or external routing problems from software running on the PC.
- It never claims that changing DNS lowers the ping to a game server whose
  address is already resolved.
- It never presents a missing ICMP reply as proof of a failed device, and it
  never presents a `*` hop in a route trace as proof of packet loss.
- It separates locally fixable problems from problems that require the router,
  the ISP or the physical link to be repaired.

If you are looking for a tool that promises lower ping with one click, NetPulse
is not it — and no honest tool is.

---

## Features

- **Local link diagnostics (A):** active adapter, media type (Ethernet/Wi-Fi),
  link state, negotiated link speed, IPv4/IPv6 addresses, default gateway, DNS
  servers, DHCP state and MTU where Windows reports them.
- **Gateway latency test (B):** at least 30 ICMP probes to the local router by
  default, with per-sample timings and full statistics.
- **Internet latency test (C):** probes to at least two configurable public
  targets (defaults `1.1.1.1` and `8.8.8.8`), plus optional TCP connectivity
  probes to distinguish ICMP filtering from a real outage.
- **DNS diagnostics (D):** resolves `google.com` and `cloudflare.com` by default
  and measures lookup time; optional comparison against public resolvers when the
  user enables it.
- **Route diagnostics (E):** a bounded **tracert** with hop addresses and three
  RTT samples per hop, explained with the caveat that `*` hops are usually ICMP
  filtering rather than real loss.
- **Wi-Fi diagnostics (F):** SSID, BSSID, signal percentage, radio type, band,
  channel and receive/transmit link rates where available.
- **Optional download speed test (G):** never runs automatically, never uses
  arbitrary third-party speed-test servers, and only downloads from a URL the
  user explicitly provides and consents to.
- **Rule-based diagnosis engine:** transparent findings with Finding, Evidence,
  Confidence (Low/Medium/High), Meaning, Recommended next action and "What the
  app cannot verify".
- **Report export:** JSON (machine-readable), TXT (paste into an e-mail) and HTML
  (self-contained and printable), with user-selectable redaction of sensitive
  fields and a preview before export.
- **Local history:** a Diagnostics History page stores runs locally and can be
  cleared at any time.
- **Windows Network Settings page:** read-first, explains trade-offs, requires an
  explicit confirmation, writes a snapshot before any change and can restore it.
- **No administrator rights required** for normal diagnosis, no auto-start, no
  telemetry, and nothing is uploaded.

---

## Screenshots

NetPulse does not ship mock-ups or fabricated images. Screenshots must be
produced from the **running** application. To launch it and take your own:

```powershell
python -m app
```

<!--
  Screenshots are captured from the running application, not committed as
  placeholders. To contribute screenshots, run the app and save PNG files with
  these exact names so the README renders them automatically.

  docs/images/dashboard.png          - Dashboard after a completed diagnosis
  docs/images/history.png            - Diagnostics History page
  docs/images/network-settings.png   - Windows Network Settings page
  docs/images/export-dialog.png      - Export dialog with the redaction preview
  docs/images/about.png              - About dialog
-->

> The images below are intentionally left empty until real screenshots are
> captured from a running build. Drop the files at the paths shown in the comment
> above and they will appear here.

<!-- ![Dashboard](docs/images/dashboard.png) -->
<!-- ![Diagnostics History](docs/images/history.png) -->
<!-- ![Windows Network Settings](docs/images/network-settings.png) -->
<!-- ![Export dialog](docs/images/export-dialog.png) -->

---

## Requirements

- **Windows 10 or Windows 11**
- **Python 3.12 or newer**

NetPulse uses only the Python standard library for its diagnostics, plus two
runtime dependencies:

- `PySide6` — the desktop GUI
- `psutil` — adapter and interface information

`dnspython` is **optional**: when it is installed, NetPulse can time each
configured DNS resolver separately. Without it, NetPulse measures the system
resolver only and says so in the report.

---

## Install

From the repository root, in **PowerShell**:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

For development (tests, linting and packaging tools):

```powershell
python -m pip install -r requirements-dev.txt
```

Optional, for per-server DNS timing:

```powershell
python -m pip install "dnspython>=2.4"
```

---

## Run

```powershell
python -m app
```

The application starts without administrator rights; normal diagnosis works at
the standard user privilege level.

---

## Run the tests

The unit tests are offline: they do not require a live network connection.

```powershell
python -m pytest -q
```

---

## Lint

NetPulse uses Ruff for linting, configured in `pyproject.toml` (line length 100).

```powershell
python -m ruff check .
```

---

## Build a Windows executable

NetPulse uses PyInstaller. The project spec file is `netpulse.spec` and produces
a **one-folder, windowed** build of `app/__main__.py`.

```powershell
python -m pip install "pyinstaller>=6.0"
python -m PyInstaller netpulse.spec --noconfirm
```

The result is written to:

```
dist/NetPulse/NetPulse.exe
```

See [docs/BUILD.md](docs/BUILD.md) for the single-file variant, verification
steps, and what the build deliberately does **not** do (no code signing, no
installer, no auto-update).

---

## Data & privacy

Everything NetPulse writes stays on your machine, under your per-user data
directory:

```
%LOCALAPPDATA%\NetPulse
```

- `settings.json` — your settings
- `history.json` — your local diagnosis history
- `snapshots\` — restore points written before any network setting change
- `reports\` — reports you export (if you choose that location)

NetPulse has **no telemetry, no analytics, no accounts and no automatic
uploads**. It never adds itself to Windows startup. Exported reports contain
personal information such as IP addresses, adapter names and Wi-Fi SSID; the
export dialog lists every sensitive field and lets you redact any of them before
writing the file. See [docs/PRIVACY.md](docs/PRIVACY.md) for the full list.

---

## Project structure

```
app/                 Application entry point (python -m app)
app/ui/              PySide6 user interface: Dashboard, Diagnostics History,
                     Windows Network Settings, Settings, Export dialog, About
app/core/            Diagnostic models, latency statistics, settings, history,
                     paths, host info and the diagnosis engine
app/network/         ICMP/ping, ping parsing, adapters, Wi-Fi, DNS, route,
                     TCP probes, the optional speed test, safe subprocess
                     execution, privilege helpers and input validation
app/optimization/    Read-only network checks ("Windows Network Settings") and
                     the reversible, snapshot-protected actions
app/reporting/       JSON, TXT and HTML writers, redaction and formatting
tests/               Offline unit tests
docs/                User guide, troubleshooting, privacy and build guides
```

---

## How the diagnosis works

NetPulse runs every independent test on a bounded thread pool, reports progress
as tests complete, and can be cancelled at any time without freezing the UI. No
test changes a system setting.

- **A — Local adapter and link.** Reads the active adapter, its type, link speed,
  addresses, gateway, DNS servers and DHCP state. Wi-Fi additionally provides the
  SSID, signal percentage and link rates. Windows CIM property names are always
  English, so parsing stays correct on non-English Windows; adapter records are
  emitted in a delimited form that is unit tested.
- **B — Gateway ping.** Pings the default gateway at least 30 times by default
  and records every sample, timeout, minimum, maximum, average, median, jitter
  and packet loss. A silent gateway is reported as "not measurable / ICMP may be
  blocked", never as an automatic router failure.
- **C — Internet latency.** Probes at least two public targets (default
  `1.1.1.1` and `8.8.8.8`) with a configurable sample count (default 30) and a
  delay between probes. Optional TCP probes to well-known ports help separate
  "ICMP is filtered" from "the internet is unreachable".
- **D — DNS.** Lists the configured resolvers and measures how long name
  lookups take. With `dnspython` installed it can time each resolver separately,
  and it can optionally compare public resolvers against your configured ones —
  but only when you enable that comparison.
- **E — Route.** Runs a hard-timeout, cancellable `tracert`, preserving hop
  numbers, addresses and three RTT samples per hop.
- **F — Wi-Fi.** Reads radio details when Wi-Fi is present and explains the
  difference between Wi-Fi link rate and internet bandwidth.
- **G — Optional speed test.** Only runs when you provide a URL and explicitly
  confirm consent. It performs a direct HTTP(S) GET to that URL for a bounded
  time and reports the measured throughput. It never downloads from arbitrary
  third-party servers and never runs automatically.

### How the latency numbers are calculated

The formulas are implemented in `app/core/stats.py` and documented in
[docs/USER_GUIDE.md](docs/USER_GUIDE.md):

- Packet loss: `loss = lost / sent * 100`
- Jitter: the mean absolute difference between **consecutive successful** RTTs;
  lost probes are skipped, not treated as `0 ms`.
- Mean, median and **population** standard deviation of the successful RTTs.

---

## Safety and limitations

- Subprocesses always use **argument arrays with `shell=False`** and a timeout.
- Targets (hostnames, IP addresses, URLs) are validated before they are used;
  validated values are never interpreted as shell tokens.
- Normal diagnosis needs **no administrator rights**.
- There is **no background service**, no auto-start and no network listener —
  NetPulse runs no network service.
- On the **Windows Network Settings** page, NetPulse reads first, explains the
  trade-offs, requires an explicit confirmation, writes a snapshot before any
  change and can restore it. It **never** disables Firewall, Defender, IPv6 or
  security features, never forces link speed, duplex or MTU, and never runs
  `netsh` resets automatically.
- NetPulse cannot see router internals, ISP line statistics, radio-link metrics,
  or physical cable/connector condition. Where that matters, the finding says so
  explicitly instead of guessing.

See [docs/USER_GUIDE.md](docs/USER_GUIDE.md) and
[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for how to interpret results
and how to prepare a report for your ISP.

---

## Contributing

Contributions are welcome. Please read
[CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. All
participants are expected to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

Security issues should be reported privately as described in
[SECURITY.md](SECURITY.md).

---

## License

NetPulse is released under the [MIT License](LICENSE).
