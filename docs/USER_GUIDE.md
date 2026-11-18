# NetPulse User Guide

This guide explains what every page does, how to run a diagnosis, and how to read
the results honestly. NetPulse measures your connection and explains what it
found; it does not promise to repair problems that live outside your PC.

---

## The pages

NetPulse has four main pages, plus an Export dialog and an About dialog.

### Dashboard

The Dashboard is where a diagnosis runs and where its results appear.

- An **overall status banner** summarises the run (Good, Informational, Warning,
  Critical or Unknown) together with a one-line headline.
- **Cards** summarise the individual areas: Gateway (PC to router), Internet
  latency targets, DNS, Wi-Fi/Ethernet, and Route.
- The **active adapter** is shown with its type, link speed, local IP, gateway and
  DNS servers where Windows reports them. A value that is unavailable is shown as
  unavailable — it is never invented.
- **Start Diagnosis** begins a run; **Stop** cancels it. The tests run on a
  background pool, so the window stays responsive and you can stop at any time.
- A **progress indicator** advances as each test finishes.

### Diagnostics History

Lists your previous runs, newest first, with the time, overall status, headline
and a few key numbers. You can open an entry to review the full report data, and
you can **Clear History** to delete everything NetPulse has stored locally.

### Windows Network Settings

Read-first. NetPulse collects your current Windows network settings, explains
what each value means and what the trade-offs of changing it would be, and only
then offers any change. No change is ever applied without your explicit
confirmation, every change writes a snapshot first, and snapshots can be
restored. See *Using the Windows Network Settings page safely* below.

### Settings

Theme, probe counts and intervals, timeouts, the internet/DNS/route targets, the
optional public-DNS comparison, the optional speed test and the rating
thresholds. Settings are stored locally in `settings.json`.

### Export dialog

Choose a format (JSON, TXT or HTML), review the list of potentially identifying
fields NetPulse found in the report, select which to redact, and preview the
result before writing the file.

### About dialog

Shows the version, the project URL and the diagnostic disclaimer.

---

## Running a diagnosis

1. Make sure you are connected the way you normally are (Ethernet, Wi-Fi, …). If
   you are troubleshooting Wi-Fi, run one test on Wi-Fi and one on Ethernet so you
   can compare.
2. Close heavy downloads or streams if you want a clean baseline.
3. Click **Start Diagnosis**.
4. Wait for the progress indicator to finish. You can click **Stop** to cancel;
   cancelled runs are clearly marked as partial.
5. Read the banner, then the cards, then the findings.
6. If you plan to contact your ISP, export a report (see below).

A single short test cannot capture problems that only happen at other times of
day. For intermittent issues, run the diagnosis more than once and compare the
history.

---

## Reading the ratings

Each card and each finding is rated with one of:

| Rating | Meaning |
| ------ | ------- |
| **Good** | The measurement is within normal ranges. |
| **Informational** | Worth knowing, but not a problem on its own. |
| **Warning** | Something is outside the normal range and is worth investigating. |
| **Critical** | A clear problem was measured and should be investigated. |
| **Unknown** | There was not enough data to judge. |

The overall status is the **worst** rating produced by the run. A "Good" overall
status means the numbers stayed within range during the test window — it does not
guarantee your connection is fast, and it does not rule out problems at other
times.

---

## Reading the cards

- **Gateway (PC to router).** How your PC reaches your own router. A round trip
  to your own router should normally stay in the low single-digit milliseconds.
  Latency or loss here points at the local link (Wi-Fi, cable, port) or at the
  router. A silent gateway is reported as "not measurable / ICMP may be blocked",
  not as a failed router, because many routers rate-limit or block ping.
- **Internet latency targets.** How your PC reaches public targets (default
  `1.1.1.1` and `8.8.8.8`). Compare this with the gateway card: a clean gateway
  plus a poor internet result points beyond your router; a poor gateway makes
  every internet result less reliable.
- **DNS.** How long it takes to turn a name into an IP address. DNS affects how
  quickly a page starts loading, not the ping to a server whose address is already
  resolved.
- **Wi-Fi / Ethernet.** The radio or link details. Wi-Fi link rates are radio
  negotiation figures, not internet bandwidth: a high link rate does not mean a
  fast connection, and a low signal causes latency spikes and loss even when the
  internet itself is healthy.
- **Route.** The path taken through routers to the target, with up to three RTT
  samples per hop.

---

## Reading a finding

Every finding has the same six parts, so nothing is hidden:

1. **Finding** — the conclusion in one line.
2. **Evidence** — the actual measured values behind it (for example
   `8.8.8.8: avg 42.1 ms, loss 6.67%, jitter 18.3 ms`).
3. **Confidence** — Low, Medium or High. Low means the measurement or the data
   cannot support a firm conclusion; treat it as a hint, not a verdict.
4. **What this may mean** — the plausible causes of the finding.
5. **Recommended next action** — the safest useful step to take next.
6. **What NetPulse cannot verify** — an explicit statement of the limit of the
   measurement, for example that NetPulse cannot read your router's log or your
   ISP's line statistics.

A finding never claims NetPulse can repair ISP congestion, radio signal, cabling
or router hardware.

---

## How the latency numbers are calculated

All per-target statistics are computed from the individual probes:

- **Packet loss** = `lost / sent * 100`, where `lost` is the number of probes that
  did not return a reply.
- **Jitter** = the mean absolute difference between **consecutive successful**
  RTTs. Lost probes are skipped rather than counted as `0 ms`, so a single lost
  probe in the middle does not create a fake jitter spike.
- **Mean** and **median** are taken over the successful RTTs.
- **Standard deviation** is the **population** standard deviation of the successful
  RTTs (dividing by *N*, not *N − 1*).

These formulas are implemented in `app/core/stats.py` and are the same ones the
application displays and exports.

---

## Reading the route trace

The route trace shows each hop's number, address (when the router answered) and
up to three RTT samples.

A `*` at a hop means that router did not return a TTL-expired ICMP reply. Routers
frequently deprioritise or block such replies, so:

- **A `*` hop is not proof of packet loss** for normal traffic. The trace simply
  became unknown at that point.
- Judge loss from the **end-to-end** latency tests, not from single `*` hops.
- Do not report a `*` hop to your ISP as a fault on its own.

---

## Using the Windows Network Settings page safely

This page changes nothing until you tell it to, and every change is reversible
where Windows allows it.

1. **Read.** NetPulse collects the current settings and shows each one with an
   explanation. Settings that are already at the Windows default are marked as
   such; settings NetPulse could not read are shown as unavailable.
2. **Understand the trade-off.** Any changeable setting is described with what it
   does and what it can cost you. For example, changing DNS can make pages start
   loading sooner but never lowers the ping to a server whose address is already
   resolved.
3. **Confirm.** Nothing is applied without an explicit confirmation. Changes that
   need administrator rights ask you to restart elevated first; NetPulse does not
   elevate on its own.
4. **Snapshot.** Immediately before a change, NetPulse writes a snapshot of the
   previous value to `%LOCALAPPDATA%\NetPulse\snapshots\`.
5. **Restore.** You can restore a snapshot to put the previous value back. Some
   advanced resets (Winsock, TCP/IP) are destructive and **cannot** be undone
   automatically; NetPulse says so and asks you to confirm them separately.

NetPulse **never** disables Firewall, Defender, IPv6 or other security features,
**never** forces link speed, duplex or MTU, and **never** runs `netsh` resets
automatically.

---

## Exporting a report for your ISP

1. Finish a diagnosis.
2. Open the Export dialog and choose **TXT** (easiest to paste into an e-mail),
   **HTML** (nicely formatted and printable) or **JSON** (full machine-readable
   data).
3. Review the list of sensitive fields. **Redact** anything you do not want to
   share — your computer name, local IP addresses, gateway, DNS servers, MAC
   addresses, adapter names/descriptions, Wi-Fi SSID/BSSID, route hop addresses
   and the speed-test URL can all be removed. Redaction also scrubs those values
   from the sentences in the report.
4. Save the file, then attach it to your support request.

When you send a report to your ISP, the most useful sections are the **host**
summary, the **gateway** and **internet latency** statistics (average, jitter and
loss), the **DNS** results and the **route trace**, together with the timestamps
so they can match your report to their logs. See
[TROUBLESHOOTING.md](TROUBLESHOOTING.md) for what each symptom most likely means.

---

## Default rating thresholds

NetPulse rates numbers using the thresholds below (from `DEFAULT_THRESHOLDS` in
`app/core/stats.py`). You can adjust them in Settings; the values shown are the
defaults.

| Setting | Warn at | Critical at |
| ------- | ------- | ----------- |
| Internet latency (average) | ≥ 80 ms | ≥ 150 ms |
| Jitter | ≥ 30 ms | ≥ 60 ms |
| Packet loss | ≥ 1 % | ≥ 5 % |
| Gateway latency (average) | ≥ 10 ms | ≥ 30 ms |
| Gateway packet loss | ≥ 1 % | ≥ 5 % |
| DNS lookup (average) | ≥ 150 ms | ≥ 400 ms |
| Wi-Fi signal | < 55 % | < 35 % |
| Ethernet slow link (informational) | ≤ 100 Mbps | — |

A value is "Good" when it is below the warn threshold; it is "Warning" when it
reaches the warn threshold but not the critical one, and "Critical" when it
reaches the critical threshold.
