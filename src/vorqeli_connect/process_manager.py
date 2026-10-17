"""Safe lifecycle for one user-selected external Windows executable."""
import subprocess
from pathlib import Path

class ModuleManager:
    def __init__(self):
        self._process = None
        self._executable = None

    @property
    def running(self):
        return self._process is not None and self._process.poll() is None

    @property
    def executable(self):
        return self._executable

    @property
    def pid(self):
        return self._process.pid if self.running else None

    @property
    def exit_code(self):
        return None if self._process is None else self._process.poll()

    def start(self, executable):
        if self.running:
            raise RuntimeError("Модуль уже запущен")
        path = Path(executable).expanduser().resolve(strict=True)
        if not path.is_file() or path.suffix.lower() != ".exe":
            raise ValueError("Выберите исполняемый файл .exe")
        self._process = subprocess.Popen(
            [str(path)], cwd=str(path.parent), shell=False,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._executable = str(path)
        return self._process.pid

    def stop(self, timeout=5):
        if not self.running:
            return False
        self._process.terminate()
        try:
            self._process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=timeout)
        return True

    def close(self):
        self.stop()
