# NetPulse Privacy Policy

NetPulse is a local diagnostic tool. It collects network measurements on your
machine, explains them to you, and stores what it needs locally. It has **no
telemetry, no analytics, no account and no automatic uploads**.

---

## What is stored locally

Everything NetPulse writes stays in your per-user data directory:

```
%LOCALAPPDATA%\NetPulse
```

| Path | What it contains |
| ---- | ---------------- |
| `settings.json` | Your settings: theme, probe counts and intervals, timeouts, targets, and rating thresholds. |
| `history.json` | Your local diagnosis history (summary values plus the report data of each run). |
| `snapshots\` | Restore points written immediately before any network setting change. |
| `reports\` | Reports you choose to export (if you save them to this location). |

You can delete any of these at any time. The **Clear History** action on the
Diagnostics History page removes your stored history, and deleting the
`%LOCALAPPDATA%\NetPulse` folder removes everything.

An alternative data directory can be set with the `NETPULSE_DATA_DIR` environment
variable; NetPulse uses it instead of `%LOCALAPPDATA%\NetPulse` when it is set.

---

## What is never collected

NetPulse does **not** collect, store or transmit:

- any data that leaves your machine — there is no upload of any kind;
- usage analytics, crash reports, statistics or identifiers;
- account information, passwords, Wi-Fi keys or other credentials;
- browser history, files or content;
- your public IP address (NetPulse does not look it up).

---

## What NetPulse does not do

- **No telemetry.** Nothing is reported back to the developers or to anyone else.
- **No analytics.** There is no tracking of how you use the application.
- **No automatic uploads.** Reports are written only when you export them, and
  only to the location you choose. Nothing is sent automatically.
- **No auto-start.** NetPulse does not add itself to Windows startup.
- **No network service.** NetPulse opens no listening socket and installs no
  background service. The only network traffic it generates is the probes you ask
  for (ICMP, TCP, DNS and the optional speed test).

---

## What an exported report contains

A report is the record of one diagnosis. Depending on what was measured, it can
include:

- the app version, timestamps and the test duration;
- your Windows version, build and architecture, and whether NetPulse ran as
  administrator;
- your **computer name**;
- adapter details: **adapter name(s)** and **model/description**, media type,
  link speed, **MAC address(es)**, **local IPv4** and **IPv6** addresses, and
  **default gateway**;
- **DNS server** addresses and DNS lookup results;
- the internet and gateway latency statistics (average, jitter, loss and the
  individual probe results) and TCP connectivity results;
- Wi-Fi details when present: **SSID**, **BSSID**, signal, band, channel and link
  rates;
- the **route trace** with **hop addresses**;
- the optional speed test **URL** and its measured throughput, if you ran it;
- any configuration changes NetPulse recorded (with before/after values);
- the findings, their evidence, confidence and recommendations.

### Redactable fields

Before writing a report, the Export dialog lists every potentially identifying
field it found and lets you select which to redact:

| Field | What it is |
| ----- | ---------- |
| Computer name | The Windows computer name of this PC. |
| Local IPv4 address(es) | Private IPv4 addresses of the active adapter. |
| Local IPv6 address(es) | Global IPv6 addresses of the active adapter (link-local addresses are already excluded). |
| Default gateway | The address of your router on the local network. |
| DNS server addresses | The DNS resolvers configured on the adapter. |
| Adapter MAC address(es) | Hardware addresses of the network adapters. |
| Adapter name(s) | Windows names of the network adapters. |
| Adapter model/description | Adapter model strings, which can identify your hardware. |
| Wi-Fi network name (SSID) | The Wi-Fi network you were connected to. |
| Wi-Fi access point MAC (BSSID) | The hardware address of the Wi-Fi access point. |
| Public IP address (if discovered) | Listed for completeness; NetPulse does not look up your public IP. |
| Route trace hop addresses | Router addresses along the traced path, which can identify your ISP and region. |
| Speed test URL | The download URL you entered for the optional speed test. |

### How redaction works

1. Finish a diagnosis and open the Export dialog.
2. Choose the format (JSON, TXT or HTML).
3. Review the list above. Fields that are present in the report are offered for
   selection; the dialog shows the values it found.
4. Select the fields to redact. Redaction replaces the selected values with clear
   placeholders such as `[redacted-ipv4]` or `[redacted-ssid]`.
5. Redaction also scrubs those values from the sentences in the report (for
   example the diagnosis evidence), except for very short or generic network words
   that would make the report unreadable if replaced.
6. Preview the result, then save the file.

Redaction is performed locally, in memory, before the file is written. Nothing is
transmitted.

---

## The optional speed test

The optional download speed test is the only feature that can contact a server
you did not probe as part of the diagnosis. It sends a single HTTP(S) GET to a URL
**you** provide, and only after you enable the feature and confirm consent in
Settings. It never runs automatically and never downloads from arbitrary
third-party speed-test servers. The URL stays on your machine and appears in a
report only if you export one; you can redact it.

---

## Summary

NetPulse is designed so that privacy is a property of the design, not a setting:

- everything stays on your machine;
- nothing is uploaded;
- nothing runs in the background;
- nothing starts automatically;
- you control exactly what a report contains before you share it.
