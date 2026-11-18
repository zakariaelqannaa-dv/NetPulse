"""DNS diagnostics.

Per-server measurements use ``dnspython`` when it is installed (it can target a
specific resolver). Without it NetPulse measures the system resolver only and
clearly reports that per-server testing is unavailable.

NetPulse never changes DNS servers as part of a diagnosis.
"""

from __future__ import annotations

import socket
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field

from app.core.cancellation import CancellationToken
from app.core.models import DnsQueryResult, DnsTestResult, TestStatus
from app.network.validation import is_valid_ip

try:  # pragma: no cover - exercised by an explicit availability test
    import dns.exception  # type: ignore
    import dns.resolver  # type: ignore

    HAS_DNSPYTHON = True
except ImportError:  # pragma: no cover
    dns = None  # type: ignore
    HAS_DNSPYTHON = False

DEFAULT_HOSTNAMES = ["google.com", "cloudflare.com"]
PUBLIC_RESOLVERS = {"cloudflare": "1.1.1.1", "google": "8.8.8.8"}

ProgressCallback = Callable[[int, int], None]


@dataclass
class DnsConfig:
    hostnames: list[str] = field(default_factory=lambda: list(DEFAULT_HOSTNAMES))
    servers: list[str] = field(default_factory=list)
    timeout_ms: int = 3000
    include_public_resolvers: bool = False
    public_resolvers: list[str] = field(default_factory=list)

    def clamped(self) -> DnsConfig:
        servers = [s for s in self.servers if is_valid_ip(s)]
        public = [s for s in (self.public_resolvers or list(PUBLIC_RESOLVERS.values())) if is_valid_ip(s)]
        return DnsConfig(
            hostnames=[h for h in self.hostnames if h][:10] or list(DEFAULT_HOSTNAMES),
            servers=servers,
            timeout_ms=max(200, min(int(self.timeout_ms), 10000)),
            include_public_resolvers=bool(self.include_public_resolvers),
            public_resolvers=public,
        )


def query_with_dnspython(server: str, hostname: str, timeout_s: float) -> DnsQueryResult:
    """Resolve ``hostname`` against a specific ``server`` using dnspython."""
    result = DnsQueryResult(server=server, hostname=hostname)
    if not HAS_DNSPYTHON:  # pragma: no cover - guarded by the caller
        result.error = "dnspython is not installed"
        return result

    resolver = dns.resolver.Resolver(configure=False)  # type: ignore[union-attr]
    resolver.nameservers = [server]
    resolver.timeout = timeout_s
    resolver.lifetime = timeout_s
    started = time.monotonic()
    try:
        answers = resolver.resolve(hostname, "A")  # type: ignore[union-attr]
        result.duration_ms = (time.monotonic() - started) * 1000.0
        result.addresses = sorted({str(rdata.address) for rdata in answers})
        result.ok = bool(result.addresses)
        if not result.ok:
            result.error = "No A records returned"
    except dns.resolver.NXDOMAIN:  # type: ignore[union-attr]
        result.duration_ms = (time.monotonic() - started) * 1000.0
        result.error = "NXDOMAIN (name does not exist)"
    except dns.resolver.NoNameservers:  # type: ignore[union-attr]
        result.duration_ms = (time.monotonic() - started) * 1000.0
        result.error = "No usable nameservers"
    except dns.exception.Timeout:  # type: ignore[union-attr]
        result.error = f"Query timed out after {timeout_s:.1f}s"
    except Exception as exc:  # noqa: BLE001 - dnspython raises many subclasses
        result.error = f"{type(exc).__name__}: {exc}"
    return result


def query_system_resolver(hostname: str, timeout_s: float) -> DnsQueryResult:
    """Measure the system resolver using ``getaddrinfo`` with a hard timeout."""
    result = DnsQueryResult(server="system", hostname=hostname)
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(socket.getaddrinfo, hostname, None, 0, socket.SOCK_STREAM)
        try:
            infos = future.result(timeout=timeout_s)
        except FutureTimeoutError:
            result.error = f"System resolver timed out after {timeout_s:.1f}s"
            return result
        except socket.gaierror as exc:
            result.duration_ms = (time.monotonic() - started) * 1000.0
            result.error = f"Resolution failed: {exc}"
            return result
        except Exception as exc:  # noqa: BLE001
            result.error = f"{type(exc).__name__}: {exc}"
            return result
    result.duration_ms = (time.monotonic() - started) * 1000.0
    result.addresses = sorted({str(info[4][0]) for info in infos if info[4]})
    result.ok = bool(result.addresses)
    if not result.ok:
        result.error = "No addresses returned"
    return result


def run_dns_test(
    config: DnsConfig,
    token: CancellationToken | None = None,
    progress: ProgressCallback | None = None,
    resolver_fn: Callable[[str, str, float], DnsQueryResult] | None = None,
) -> DnsTestResult:
    """Run the DNS test suite and rate the outcome."""
    config = config.clamped()
    started = time.monotonic()
    outcome = DnsTestResult(
        configured_servers=list(config.servers),
        public_comparison_enabled=config.include_public_resolvers,
    )
    timeout_s = config.timeout_ms / 1000.0

    servers: list[tuple[str, bool]] = [(s, False) for s in config.servers]
    if config.include_public_resolvers:
        servers.extend((s, True) for s in config.public_resolvers if s not in config.servers)

    per_server = HAS_DNSPYTHON and resolver_fn is None
    if resolver_fn is None and not per_server:
        servers = [("system", False)]

    total = len(servers) * len(config.hostnames)
    if total == 0:
        outcome.status = TestStatus.UNSUPPORTED
        outcome.message = "No DNS servers were configured and no query targets were available."
        return outcome

    done = 0
    for server, is_public in servers:
        if token is not None and token.is_cancelled():
            outcome.status = TestStatus.CANCELLED
            outcome.message = "DNS test was cancelled."
            outcome.duration_ms = (time.monotonic() - started) * 1000.0
            return outcome
        for hostname in config.hostnames:
            if token is not None and token.is_cancelled():
                outcome.status = TestStatus.CANCELLED
                outcome.message = "DNS test was cancelled."
                outcome.duration_ms = (time.monotonic() - started) * 1000.0
                return outcome
            if resolver_fn is not None:
                query = resolver_fn(server, hostname, timeout_s)
            elif per_server:
                query = query_with_dnspython(server, hostname, timeout_s)
            else:
                query = query_system_resolver(hostname, timeout_s)
            query.is_public_resolver = is_public
            outcome.queries.append(query)
            done += 1
            if progress is not None:
                progress(done, total)

    outcome.duration_ms = (time.monotonic() - started) * 1000.0
    _rate_dns_result(outcome, config)
    return outcome


def _rate_dns_result(outcome: DnsTestResult, config: DnsConfig) -> None:
    configured_queries = [q for q in outcome.queries if not q.is_public_resolver]
    successful = [q for q in configured_queries if q.ok and q.duration_ms is not None]
    if not configured_queries:
        outcome.status = TestStatus.UNSUPPORTED
        outcome.message = "No DNS queries were executed."
        return

    durations = [float(q.duration_ms) for q in successful]
    if durations:
        outcome.average_ms = round(sum(durations) / len(durations), 3)
        outcome.slowest = max(successful, key=lambda q: float(q.duration_ms or 0.0))

    if not successful:
        outcome.status = TestStatus.CRITICAL
        outcome.message = "Every DNS lookup failed. The configured resolver(s) are not answering."
        return

    failures = len(configured_queries) - len(successful)
    if failures:
        outcome.status = TestStatus.WARNING
        outcome.message = f"{failures} of {len(configured_queries)} DNS lookups failed or timed out."
        return

    thresholds = {"warn": 150.0, "critical": 400.0}
    average = outcome.average_ms or 0.0
    if average >= thresholds["critical"]:
        outcome.status = TestStatus.CRITICAL
        outcome.message = f"DNS lookups are very slow (average {average:.0f} ms)."
    elif average >= thresholds["warn"]:
        outcome.status = TestStatus.WARNING
        outcome.message = f"DNS lookups are slower than expected (average {average:.0f} ms)."
    else:
        outcome.status = TestStatus.OK
        outcome.message = f"DNS lookups answered normally (average {average:.0f} ms)."


def describe_dns_capability() -> str:
    if HAS_DNSPYTHON:
        return "Per-server DNS timing is available (dnspython installed)."
    return (
        "dnspython is not installed, so NetPulse measures the system resolver only. "
        "Per-server DNS timing is unavailable."
    )


__all__ = [
    "DEFAULT_HOSTNAMES",
    "PUBLIC_RESOLVERS",
    "DnsConfig",
    "HAS_DNSPYTHON",
    "describe_dns_capability",
    "query_system_resolver",
    "query_with_dnspython",
    "run_dns_test",
]
