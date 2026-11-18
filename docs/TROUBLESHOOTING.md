# NetPulse Troubleshooting Guide

This guide is organised by symptom. For each one it explains what NetPulse
shows, what it most likely means, what you can safely try locally, what needs the
router, your ISP or the physical link, and what NetPulse cannot determine.

A reminder before you start:

- **Bandwidth is not latency.** A 200 Mbps download connection can still have
  terrible ping if the path is congested or unstable. High speed does not
  guarantee low ping.
- **Bandwidth, latency, jitter and loss are different things.** Bandwidth is how
  much data fits through; latency is the round-trip delay; jitter is how much the
  delay varies; loss is how often a probe never arrives.
- **A `*` hop in a route trace is not proof of loss** (see below).
- **Changing DNS rarely fixes high game ping.** DNS only affects name resolution,
  not the ping to an address that is already resolved.

---

## High ping (high average latency)

- **What NetPulse shows:** the Gateway card and the Internet latency cards show
  high `Average RTT`. If the gateway is fast and the internet targets are slow,
  the delay is added beyond your router. If the gateway is also slow, part of the
  delay is already inside your network.
- **What it most likely means:** a busy local link or router, a congested Wi-Fi
  channel, a congested upstream link, an ISP peering/capacity problem, or a
  distant destination.
- **What you can safely do locally:** compare a Wi-Fi test with an Ethernet test;
  close heavy downloads or background synchronisation; restart the router once;
  run the diagnosis at different times of day to look for a pattern.
- **What requires the router / ISP / physical link:** bufferbloat inside the
  router, upstream congestion, ISP routing and peering, and saturation of a
  shared fixed-wireless sector all need the router's settings, the ISP's line
  statistics or a physical check.
- **What NetPulse cannot determine:** which individual hop adds the delay, your
  router's CPU or buffer state, and the latency your specific game or application
  sees (a public ICMP target is not the same as your game server).

---

## High jitter (unstable latency)

- **What NetPulse shows:** the Internet cards show a high `Jitter` value, and a
  finding reports the worst jitter. Jitter is the mean absolute difference
  between consecutive successful RTTs, so lost probes do not create a fake spike.
- **What it most likely means:** congestion (especially while another device is
  downloading or uploading), a wireless link with interference or marginal signal,
  or bufferbloat on the router or upstream.
- **What you can safely do locally:** test over Ethernet; check whether the jitter
  appears only when someone else is using the connection; enable QoS for
  real-time traffic on the router if it supports it; move closer to the access
  point if you are on Wi-Fi.
- **What requires the router / ISP / physical link:** bufferbloat and traffic
  shaping usually need a router setting or an ISP-side change; sustained jitter on
  a wired link with no local load points at the ISP.
- **What NetPulse cannot determine:** the router's buffer depth, the ISP's
  traffic-shaping policy, and interference from neighbouring networks (that needs
  a spectrum/Wi-Fi survey).

---

## Packet loss

- **What NetPulse shows:** the *Packet loss* statistic on the Gateway and Internet
  cards. A finding distinguishes loss **towards the gateway** (local) from loss
  **towards public targets** (upstream). Loss towards several public targets is
  treated differently from loss towards only one.
- **What it most likely means:** loss to the **gateway** points at the local link
  — a bad cable, a marginal Wi-Fi signal, a failing port — or at the router
  itself. Loss only **beyond** the router points upstream; loss towards a single
  public target can also be that target's own network or ICMP rate limiting.
- **What you can safely do locally:** re-seat or replace the Ethernet cable; try
  a different router port; test on Ethernet instead of Wi-Fi; restart the router
  once.
- **What requires the router / ISP / physical link:** a damaged cable,
  a failing router port or router hardware, and upstream/ISP instability all need
  a physical or ISP-side check.
- **What NetPulse cannot determine:** whether loss is caused by a specific hop,
  by the destination rate-limiting ICMP, or by ISP congestion, from end-to-end
  measurements alone.

---

## No internet at all

- **What NetPulse shows:** the local-link findings (no adapter, no default route,
  no IP address or no gateway), the TCP connectivity section, and the internet
  latency cards. If TCP probes succeed while ICMP fails, NetPulse says so.
- **What it most likely means:** the adapter is down or disabled, DHCP failed, the
  cable or Wi-Fi link is down, the router's WAN is down, or ICMP is filtered while
  real traffic still works.
- **What you can safely do locally:** check Wi-Fi is enabled or the cable is
  plugged in; toggle the adapter; set the adapter back to automatic (DHCP)
  addressing if it has a static misconfiguration; restart the router once; open a
  website to confirm whether traffic actually works.
- **What requires the router / ISP / physical link:** a router with no WAN link,
  an ISP outage, or a dead adapter/cable.
- **What NetPulse cannot determine:** whether an outage is caused by your PC, the
  router or the ISP when both ICMP and TCP fail — repeat the diagnosis and verify
  with a browser.

---

## Slow page loading but fine ping (DNS)

- **What NetPulse shows:** the DNS card reports a slow *Average lookup*, often
  with a finding that says name resolution is slow while IP latency is stable.
  The Internet latency cards look normal.
- **What it most likely means:** the configured DNS resolver is slow or
  overloaded. This affects how quickly a page *starts*, not the ping to a server
  you are already connected to.
- **What you can safely do locally:** optionally enable the public-resolver
  comparison to measure the difference; if a public resolver is consistently much
  faster, changing DNS on the adapter is a safe, reversible change you can make
  from the Windows Network Settings page.
- **What requires the router / ISP / physical link:** whether the resolver itself
  is overloaded, whether the router forwards queries slowly, or whether the ISP
  applies DNS tampering.
- **What NetPulse cannot determine:** resolver caching effects, upstream
  forwarding latency, and ISP-side DNS behaviour.

Changing DNS never improves the ping to a game server whose address is already
resolved. It can only make the *initial* name lookup faster.

---

## Weak Wi-Fi signal

- **What NetPulse shows:** the Wi-Fi card shows the SSID, signal percentage, band,
  channel and link rates. A finding warns when the signal is below the warn
  (55 %) or critical (35 %) thresholds.
- **What it most likely means:** you are far from the access point, or there are
  obstructions (walls, metal, appliances) or interference. A weak radio link
  causes latency spikes, jitter and loss even when the internet itself is healthy.
- **What you can safely do locally:** move closer to the access point; remove
  obstructions; switch to the 5 GHz or 6 GHz band if available; test with an
  Ethernet cable to isolate Wi-Fi from the WAN; try a different Wi-Fi channel
  only after measuring your own environment.
- **What requires the router / ISP / physical link:** the access point's placement
  and antenna, channel congestion, and interference from neighbours, which need a
  Wi-Fi/spectrum survey.
- **What NetPulse cannot determine:** interference and neighbour congestion from a
  single adapter, and the Wi-Fi quality at other places in the building.

Wi-Fi link rates are radio negotiation figures (for example 866 Mbps), not your
internet bandwidth. A high link rate does not mean a fast connection.

---

## Ethernet stuck at 100 Mbps

- **What NetPulse shows:** the adapter card and a finding report the negotiated
  link speed (for example "Ethernet link negotiated at 100 Mbps"). Latency is not
  affected by link speed, but throughput is capped near the negotiated value.
- **What it most likely means:** a damaged or marginal cable (only two of the four
  pairs working), an old Cat5 cable, a 100 Mbps router/switch port, or an adapter
  that cannot do gigabit.
- **What you can safely do locally:** try a known-good Cat5e/Cat6 cable; plug into
  a different router port; compare the negotiated speed shown on this page after
  each change. NetPulse never forces a link speed or duplex mode, because forcing
  a speed a cable cannot support causes disconnects.
- **What requires the router / ISP / physical link:** the cable and the router
  port, which can only be confirmed physically.
- **What NetPulse cannot determine:** whether a specific cable or connector is
  electrically marginal — that needs a cable test.

---

## Short disconnects after idle

- **What NetPulse shows:** on the Windows Network Settings page, a check reports
  whether Windows is allowed to power down the adapter ("Windows may turn off the
  device"). A diagnosis may also show a burst of loss shortly after the machine
  has been idle.
- **What it most likely means:** on laptops, Windows is allowed to power down an
  idle network adapter, which commonly causes a short disconnect or a few seconds
  of packet loss after the machine has been idle.
- **What you can safely do locally:** turn off adapter power saving from the
  Windows Network Settings page. It is a safe, reversible change and NetPulse
  writes a snapshot first.
- **What requires the router / ISP / physical link:** if the dropouts persist on a
  wired link with power saving already off, the cable, port or router may be at
  fault.
- **What NetPulse cannot determine:** whether a dropout was caused by the adapter,
  the driver, the router or the ISP without logs from each.

---

## VPN / proxy leftovers

- **What NetPulse shows:** on the Windows Network Settings page, a check reports
  whether a proxy server or auto-config script is configured for your user
  account, and the adapter detail shows DNS servers that may have been left by a
  VPN.
- **What it most likely means:** a VPN, adware or a corporate configuration left
  a proxy or custom DNS setting behind, which can silently break or slow down
  internet access for normal applications. A damaged Winsock catalog (often after
  an incomplete VPN or proxy removal) can also cause odd failures.
- **What you can safely do locally:** review the proxy setting in Windows Settings
  if you did not set it on purpose — NetPulse does not change proxy settings for
  you. Reset DNS to automatic if a VPN left custom resolvers behind.
- **What requires the router / ISP / physical link:** most VPN/proxy leftovers are
  local, but a corporate proxy or a filtering resolver is usually intentional and
  should be changed only with your network administrator.
- **What NetPulse cannot determine:** whether a Winsock catalog fault (rather than
  a proxy setting) is the real cause, without a more invasive investigation.

The Winsock and TCP/IP resets are **destructive**, need a restart, and **cannot**
be undone automatically. NetPulse never runs them on its own; they are advanced,
separately confirmed actions.

---

## "ICMP blocked but TCP works"

- **What NetPulse shows:** no ICMP replies from public targets, but the TCP
  connectivity section reports successful handshakes to well-known endpoints
  (defaults `1.1.1.1:443` and `8.8.8.8:53`). A finding states that ICMP replies
  are blocked while TCP connections still work.
- **What it most likely means:** public ICMP echo is filtered somewhere on the
  path (by a firewall, the router, or the destination). Your internet is
  reachable; the ICMP-based latency and loss numbers are simply not reliable here.
- **What you can safely do locally:** rely on the TCP and DNS results in the
  report; repeat the diagnosis at another time; check whether a local firewall or
  security product blocks outbound ICMP.
- **What requires the router / ISP / physical link:** which device on the path
  filters ICMP — often the ISP or the destination, which you cannot change from
  your PC.
- **What NetPulse cannot determine:** the real latency your applications see,
  which is destination-specific and cannot be inferred from ICMP when ICMP is
  filtered.

---

## Information to send your ISP

When you contact your ISP, export a report (TXT or HTML is easiest for support)
and redact anything you would rather not share. The sections that matter most:

- **Host summary** — your Windows version and build, and your NetPulse version.
- **Timestamps** — when the test ran, so the ISP can match it against their logs.
- **Network adapters** — which adapter was active and its negotiated link speed.
- **Local gateway** — average RTT, jitter and loss between your PC and your router.
  This shows whether the problem starts inside your own network.
- **Internet latency targets** — average RTT, jitter and loss to each public
  target. This shows whether the problem is beyond your router.
- **TCP connectivity** — whether real TCP handshakes succeed even if ICMP does
  not, which separates a filtered-ping situation from a genuine outage.
- **DNS** — average lookup time and any failures.
- **Route trace** — the hops and RTT samples, plus the note that a `*` hop is not
  proof of loss.
- **Diagnosis** — the findings, their evidence and their confidence.

If you can, include **two reports taken at different times** (for example during
and outside peak hours). A pattern is far more useful to an ISP than a single
sample. Also state your connection type (fibre, cable, DSL, fixed wireless,
mobile) and whether the problem happens on Ethernet, Wi-Fi, or both.
