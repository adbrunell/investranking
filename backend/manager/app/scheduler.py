from __future__ import annotations
import os
import subprocess
import json
from datetime import datetime, time as dtime
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, pyqtSignal
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .models import ScriptConfig, AppConfig, SCRIPTS_DIR, PYTHON


class ScriptScheduler(QObject):
    log_line = pyqtSignal(str, str, str)
    script_status = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scheduler = BackgroundScheduler(daemon=True)
        self._processes: dict[str, QProcess] = {}
        self._buffers: dict[str, str] = {}
        self._configs: dict[str, ScriptConfig] = {}
        self._post_run_rpcs: list[str] = []
        self._paused = False

    def load_config(self, config: AppConfig):
        self._clear_jobs()
        self._configs.clear()
        self._post_run_rpcs = config.post_run_rpcs[:]
        for sc in config.scripts:
            self._configs[sc.name] = sc
            if sc.enabled:
                self._schedule_script(sc)

    def _clear_jobs(self):
        for job_id in [j.id for j in self._scheduler.get_jobs()]:
            self._scheduler.remove_job(job_id)

    def _schedule_script(self, sc: ScriptConfig):
        trigger = IntervalTrigger(minutes=sc.interval_minutes)
        self._scheduler.add_job(
            self._try_run,
            trigger,
            args=[sc.name],
            id=sc.name,
            replace_existing=True,
            name=sc.name,
        )
        self.log_line.emit("INFO", sc.name, f"Agendado: a cada {sc.interval_minutes}min")

    def _try_run(self, name: str):
        sc = self._configs.get(name)
        if not sc or not sc.enabled or self._paused:
            return
        if not self._is_active(sc):
            return
        if name in self._processes and self._processes[name].state() == QProcess.ProcessState.Running:
            return
        self._run_script(sc)

    def _is_active(self, sc: ScriptConfig) -> bool:
        now = datetime.now()
        if sc.active_days and now.weekday() not in sc.active_days:
            return False
        start = dtime.fromisoformat(sc.active_hours_start)
        end = dtime.fromisoformat(sc.active_hours_end)
        t = now.time()
        if start <= end:
            return start <= t <= end
        return t >= start or t <= end

    def _read_env(self) -> dict:
        env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
        env = {}
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
        return env

    def _run_script(self, sc: ScriptConfig):
        script_path = sc.full_path
        if not script_path.exists():
            self.log_line.emit("ERRO", sc.name, f"Arquivo nao encontrado: {script_path}")
            self.script_status.emit(sc.name, "error")
            return

        env = self._read_env()
        qt_env = QProcessEnvironment.systemEnvironment()
        for k, v in env.items():
            qt_env.insert(k, v)
        qt_env.insert("PYTHONUNBUFFERED", "1")

        process = QProcess()
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.setWorkingDirectory(str(SCRIPTS_DIR))
        process.setProcessEnvironment(qt_env)

        process.readyReadStandardOutput.connect(lambda p=process, n=sc.name: self._on_output(n, p))
        process.finished.connect(lambda code, status, n=sc.name: self._on_finished(n, code))

        process.start(str(PYTHON), [str(script_path)])
        self._processes[sc.name] = process
        self._buffers[sc.name] = ""
        self.log_line.emit("RUN", sc.name, "Iniciando...")
        self.script_status.emit(sc.name, "running")

    def _on_output(self, name: str, process: QProcess):
        data = process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        buf = self._buffers.get(name, "")
        lines = (buf + data).split("\n")
        self._buffers[name] = lines.pop(-1)
        for line in lines:
            line = line.strip()
            if line:
                self.log_line.emit(None, name, line)

    def _on_finished(self, name: str, code: int):
        buf = self._buffers.pop(name, "")
        if buf.strip():
            self.log_line.emit(None, name, buf.strip())

        if code == 0:
            self.log_line.emit("OK", name, "Concluido")
            self.script_status.emit(name, "ok")
        else:
            self.log_line.emit("ERRO", name, f"Codigo {code}")
            self.script_status.emit(name, "error")

        self._processes.pop(name, None)

        running = [
            n for n, p in self._processes.items()
            if p.state() == QProcess.ProcessState.Running
        ]
        if not running:
            self._run_post_rpcs()

    def _run_post_rpcs(self):
        env = self._read_env()
        api_key = env.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY")
        supabase_url = env.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
        if not api_key or not supabase_url:
            self.log_line.emit("WARN", "RPC", "SUPABASE_SERVICE_KEY/URL nao configurados")
            return
        for rpc in self._post_run_rpcs:
            try:
                headers = {
                    "apikey": api_key,
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                }
                req = (
                    f"import urllib.request,json;"
                    f"req=urllib.request.Request('{supabase_url}/rest/v1/rpc/{rpc}',"
                    f"data=b'{{}}',headers={json.dumps(headers)},method='POST');"
                    f"urllib.request.urlopen(req,timeout=120).read()"
                )
                subprocess.run(
                    [str(PYTHON), "-c", req],
                    capture_output=True, timeout=130, cwd=str(SCRIPTS_DIR),
                )
                self.log_line.emit("OK", f"RPC:{rpc}", "Executado")
            except Exception as e:
                self.log_line.emit("WARN", f"RPC:{rpc}", str(e)[:120])

    def run_now(self, name: str):
        sc = self._configs.get(name)
        if sc:
            self._run_script(sc)

    def stop_script(self, name: str):
        process = self._processes.get(name)
        if process and process.state() == QProcess.ProcessState.Running:
            process.terminate()
            self.log_line.emit("INFO", name, "Encerrando...")

    def pause(self):
        self._paused = True
        self._scheduler.pause()
        self.log_line.emit("INFO", "Sistema", "Pausado")

    def resume(self):
        self._paused = False
        self._scheduler.resume()
        self.log_line.emit("INFO", "Sistema", "Retomado")

    @property
    def is_paused(self) -> bool:
        return self._paused

    def start(self):
        self._scheduler.start()
        self._run_startup_scripts()

    def _run_startup_scripts(self):
        from PyQt6.QtCore import QTimer
        for name, sc in self._configs.items():
            if sc.enabled and self._is_active(sc):
                QTimer.singleShot(0, lambda n=name: self._try_run(n))

    def shutdown(self):
        for name, process in list(self._processes.items()):
            if process.state() == QProcess.ProcessState.Running:
                process.terminate()
                process.waitForFinished(3000)
        self._scheduler.shutdown(wait=False)

    def get_status(self, name: str) -> str:
        process = self._processes.get(name)
        if process and process.state() == QProcess.ProcessState.Running:
            return "running"
        return "idle"

    def add_script(self, sc: ScriptConfig):
        self._configs[sc.name] = sc
        if sc.enabled:
            self._schedule_script(sc)

    def remove_script(self, name: str):
        self._configs.pop(name, None)
        try:
            self._scheduler.remove_job(name)
        except Exception:
            pass
        stop = self._processes.pop(name, None)
        if stop and stop.state() == QProcess.ProcessState.Running:
            stop.terminate()

    def update_script(self, sc: ScriptConfig):
        old = self._configs.get(sc.name)
        self._configs[sc.name] = sc
        try:
            self._scheduler.remove_job(sc.name)
        except Exception:
            pass
        if sc.enabled:
            self._schedule_script(sc)
        if old and old.path != sc.path:
            stop = self._processes.pop(sc.name, None)
            if stop and stop.state() == QProcess.ProcessState.Running:
                stop.terminate()
