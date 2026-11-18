"""Diagnostic orchestration.

The engine runs every independent test on a bounded thread pool, reports
progress as tests complete and supports cancellation. It never blocks the GUI
thread and it never changes any system setting.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app import APP_VERSION
from app.core.cancellation import CancellationToken
from app.core.diagnosis import evaluate
from app.core.models import (
    ChangeRecord,
    DiagnosticReport,
    PingResult,
    TestStatus,
)
from app.core.settings import AppSettings, parse_probe
from app.core.system_info import collect_host_info
from app.network.adapter import AdapterSnapshot, collect_adapters
from app.network.dns_test import DnsConfig, run_dns_test
from app.network.icmp import BasePinger, create_pinger
from app.network.ping import PingConfig, measure_target
from app.network.route import RouteConfig, run_route_trace
from app.network.speedtest import measure_download
from app.network.tcp_probe import run_tcp_probes
from app.network.wifi import collect_wifi

ProgressCallback = Callable[[int, str | None], None]
ResultCallback = Callable[[str, Any], None]


@dataclass
class EngineDependencies:
    """Injectable collaborators so the engine can be tested without a network."""

    adapter_collector: Callable[..., AdapterSnapshot] = collect_adapters
    wifi_collector: Callable[..., Any] = collect_wifi
    pinger_factory: Callable[[CancellationToken], BasePinger] = create_pinger
    dns_runner: Callable[..., Any] = run_dns_test
    route_runner: Callable[..., Any] = run_route_trace
    tcp_runner: Callable[..., Any] = run_tcp_probes
    speed_runner: Callable[..., Any] = measure_download
    host_collector: Callable[[], Any] = collect_host_info


class DiagnosticEngine:
    """Runs the complete NetPulse diagnosis."""

    def __init__(
        self,
        settings: AppSettings,
        token: CancellationToken | None = None,
        dependencies: EngineDependencies | None = None,
        applied_changes: list[ChangeRecord] | None = None,
    ) -> None:
        self.settings = settings.normalized()
        self.token = token or CancellationToken()
        self.deps = dependencies or EngineDependencies()
        self.applied_changes = list(applied_changes or [])
        self._progress_state: dict[str, float] = {}
        self._progress_lock = threading.Lock()
        self._progress_callback: ProgressCallback | None = None
        self._result_callback: ResultCallback | None = None

    # ------------------------------------------------------------------ #
    # Progress accounting
    # ------------------------------------------------------------------ #

    def _set_progress(self, task: str, fraction: float) -> None:
        with self._progress_lock:
            self._progress_state[task] = max(0.0, min(1.0, fraction))
            total = len(self._progress_state) or 1
            completed = sum(self._progress_state.values())
        if self._progress_callback is not None:
            self._progress_callback(int(round(completed / total * 100)), task)

    def _emit(self, name: str, payload: Any) -> None:
        if self._result_callback is not None:
            self._result_callback(name, payload)

    # ------------------------------------------------------------------ #
    # Tasks
    # ------------------------------------------------------------------ #

    def _task_local(self) -> AdapterSnapshot:
        snapshot = self.deps.adapter_collector(self.token)
        self._emit("adapters", snapshot)
        self._set_progress("local", 1.0)
        return snapshot

    def _task_wifi(self) -> Any:
        wifi = self.deps.wifi_collector(self.token)
        self._emit("wifi", wifi)
        self._set_progress("wifi", 1.0)
        return wifi

    def _task_gateway(self, gateway: str | None) -> PingResult:
        if not gateway:
            self._set_progress("gateway", 1.0)
            result = PingResult(
                target="(none)",
                kind="gateway",
                status=TestStatus.ERROR,
                message="No default gateway is configured, so the router could not be tested.",
            )
            self._emit("gateway", result)
            return result

        config = PingConfig(
            count=self.settings.gateway_count,
            interval_ms=self.settings.ping_interval_ms,
            timeout_ms=self.settings.ping_timeout_ms,
        )
        result = measure_target(
            gateway,
            config=config,
            token=self.token,
            pinger=self.deps.pinger_factory(self.token),
            progress=lambda done, total: self._set_progress("gateway", done / max(total, 1)),
            kind="gateway",
            thresholds=self.settings.thresholds,
        )
        self._set_progress("gateway", 1.0)
        self._emit("gateway", result)
        return result

    def _task_internet(self, target: str) -> PingResult:
        config = PingConfig(
            count=self.settings.ping_count,
            interval_ms=self.settings.ping_interval_ms,
            timeout_ms=self.settings.ping_timeout_ms,
        )
        key = f"internet:{target}"
        result = measure_target(
            target,
            config=config,
            token=self.token,
            pinger=self.deps.pinger_factory(self.token),
            progress=lambda done, total: self._set_progress(key, done / max(total, 1)),
            kind="internet",
            thresholds=self.settings.thresholds,
        )
        self._set_progress(key, 1.0)
        self._emit("internet", result)
        return result

    def _task_tcp(self) -> list[Any]:
        probes = [parse_probe(entry) for entry in self.settings.tcp_probes]
        results = self.deps.tcp_runner(probes, self.settings.tcp_timeout_ms / 1000.0)
        self._set_progress("tcp", 1.0)
        self._emit("tcp", results)
        return results

    def _task_dns(self, servers: list[str]) -> Any:
        config = DnsConfig(
            hostnames=list(self.settings.dns_hostnames),
            servers=list(servers),
            timeout_ms=self.settings.dns_timeout_ms,
            include_public_resolvers=self.settings.enable_public_dns_comparison,
            public_resolvers=list(self.settings.public_dns_servers),
        )
        result = self.deps.dns_runner(config, self.token)
        self._set_progress("dns", 1.0)
        self._emit("dns", result)
        return result

    def _task_route(self) -> Any:
        config = RouteConfig(
            target=self.settings.route_target,
            max_hops=self.settings.route_max_hops,
            probe_timeout_ms=self.settings.route_probe_timeout_ms,
        )
        result = self.deps.route_runner(config, self.token)
        self._set_progress("route", 1.0)
        self._emit("route", result)
        return result

    def _task_speed(self) -> Any:
        result = self.deps.speed_runner(
            self.settings.speed_test_url,
            max_seconds=float(self.settings.speed_test_max_seconds),
            token=self.token,
        )
        self._set_progress("speed", 1.0)
        self._emit("speed", result)
        return result

    # ------------------------------------------------------------------ #
    # Orchestration
    # ------------------------------------------------------------------ #

    def run(
        self,
        on_progress: ProgressCallback | None = None,
        on_result: ResultCallback | None = None,
    ) -> DiagnosticReport:
        """Run the diagnosis and return a populated report."""
        self._progress_callback = on_progress
        self._result_callback = on_result

        started_at = datetime.now(UTC)
        started = time.monotonic()
        report = DiagnosticReport(
            app_version=APP_VERSION,
            started_at=started_at,
            host=self.deps.host_collector(),
            applied_changes=list(self.applied_changes),
            settings_snapshot=self.settings.to_dict(),
        )

        settings = self.settings
        task_names = ["local", "wifi", "gateway"]
        task_names += [f"internet:{t}" for t in settings.internet_targets]
        if settings.enable_tcp_probes and settings.tcp_probes:
            task_names.append("tcp")
        task_names.append("dns")
        if settings.enable_route_trace:
            task_names.append("route")
        if settings.speed_test_enabled and settings.speed_test_url and settings.speed_test_consent:
            task_names.append("speed")

        with self._progress_lock:
            self._progress_state = dict.fromkeys(task_names, 0.0)
        self._set_progress("local", 0.0)

        executor = ThreadPoolExecutor(
            max_workers=max(1, settings.max_workers),
            thread_name_prefix="netpulse",
        )
        futures: dict[str, Future] = {}

        try:
            local_future = executor.submit(self._task_local)
            wifi_future = executor.submit(self._task_wifi)
            futures["local"] = local_future
            futures["wifi"] = wifi_future

            snapshot: AdapterSnapshot = _future_result(local_future, AdapterSnapshot())
            report.adapters = snapshot.adapters
            report.active_adapter = snapshot.active_adapter
            report.active_adapter_name = snapshot.active_name
            if snapshot.message:
                report.warnings.append(snapshot.message)

            gateway_ip = snapshot.active_adapter.gateway if snapshot.active_adapter else None
            dns_servers = list(snapshot.active_adapter.dns_servers) if snapshot.active_adapter else []
            if not dns_servers:
                seen: list[str] = []
                for adapter in snapshot.adapters:
                    for server in adapter.dns_servers:
                        if server not in seen:
                            seen.append(server)
                dns_servers = seen

            futures["gateway"] = executor.submit(self._task_gateway, gateway_ip)
            for target in settings.internet_targets:
                futures[f"internet:{target}"] = executor.submit(self._task_internet, target)
            if "tcp" in task_names:
                futures["tcp"] = executor.submit(self._task_tcp)
            futures["dns"] = executor.submit(self._task_dns, dns_servers)
            if "route" in task_names:
                futures["route"] = executor.submit(self._task_route)
            if "speed" in task_names:
                futures["speed"] = executor.submit(self._task_speed)

            wifi = _future_result(wifi_future, None)
            report.wifi = wifi

            report.gateway_ping = _future_result(futures["gateway"], None)
            report.internet_pings = [
                result
                for name, future in futures.items()
                if name.startswith("internet:")
                for result in [_future_result(future, None)]
                if result is not None
            ]
            if "tcp" in futures:
                report.tcp_probes = _future_result(futures["tcp"], [])
            report.dns = _future_result(futures["dns"], None)
            if "route" in futures:
                report.route = _future_result(futures["route"], None)
            if "speed" in futures:
                report.speed_test = _future_result(futures["speed"], None)

        finally:
            cancelled = self.token.is_cancelled()
            executor.shutdown(wait=True, cancel_futures=True)

        report.cancelled = cancelled
        summary = evaluate(report, settings.thresholds)
        report.diagnoses = summary.diagnoses
        report.overall_status = summary.overall_status
        report.headline = summary.headline
        report.finished_at = datetime.now(UTC)
        report.duration_ms = (time.monotonic() - started) * 1000.0

        if on_progress is not None:
            on_progress(100, "finished")
        return report

    # ------------------------------------------------------------------ #

    def cancel(self) -> None:
        """Request cancellation of the running diagnosis."""
        self.token.cancel()


def _future_result(future: Future, default: Any) -> Any:
    """Return a finished future's value, or the default if it failed/stopped."""
    try:
        value = future.result()
    except Exception:  # noqa: BLE001 - a failed test must never kill the run
        return default
    return default if value is None else value


__all__ = ["DiagnosticEngine", "EngineDependencies"]
