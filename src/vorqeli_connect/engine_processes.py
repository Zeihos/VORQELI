"""Supervise only subprocesses started by this application."""
from __future__ import annotations
from pathlib import Path
import subprocess
from typing import Optional
from .engine_adapters import LaunchSpec


class EngineProcess:
    def __init__(self, label: str):
        self.label = label
        self._proc: Optional[subprocess.Popen] = None
        self._log_handle = None
        self._run_id = 0

    @property
    def running(self) -> bool:
        alive = self._proc is not None and self._proc.poll() is None
        if not alive:
            self._close_log()
        return alive

    @property
    def run_id(self) -> int:
        """A changing token to distinguish a launch from a subsequent manual stop."""
        return self._run_id

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self.running else None

    @property
    def exit_code(self) -> int | None:
        return None if self._proc is None else self._proc.poll()

    def start(self, spec: LaunchSpec, log_path: Path, env: dict[str, str] | None = None) -> int:
        if self.running:
            raise RuntimeError(f"{self.label} уже запущен")
        if self._log_handle:
            self._log_handle.close()
            self._log_handle = None
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # Rotate older logs on the next launch (a currently running process is not rotated).
        if log_path.is_file() and log_path.stat().st_size >= 2 * 1024 * 1024:
            backup = log_path.with_name(log_path.name + ".old")
            log_path.replace(backup)
        # Binary log capture: no stdout pipe to deadlock and no unbounded event-list memory.
        log = log_path.open("ab")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            process = subprocess.Popen(
                list(spec.argv), cwd=str(spec.cwd), stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, shell=False,
                creationflags=flags, env=env,
            )
        except Exception:
            log.close()
            raise
        self._log_handle = log
        self._proc = process
        self._run_id += 1
        return process.pid

    def stop(self, timeout: float = 5) -> bool:
        self._run_id += 1
        if not self.running:
            self._close_log()
            return False
        try:
            try:
                self._proc.terminate()
            except ProcessLookupError:
                pass  # Already exited between running() and terminate().
            try:
                self._proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                try:
                    self._proc.kill()
                except ProcessLookupError:
                    pass
                self._proc.wait(timeout=timeout)
            return True
        finally:
            self._close_log()

    def _close_log(self):
        if self._log_handle:
            self._log_handle.close()
            self._log_handle = None

    def close(self):
        self.stop()
