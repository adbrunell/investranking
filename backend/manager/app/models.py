from __future__ import annotations
import json
from copy import deepcopy
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "data-updates"
PYTHON = Path(__file__).resolve().parent.parent.parent.parent / "backend" / ".venv" / "Scripts" / "pythonw.exe"

DIAS_SEMANA = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]
DIAS_SEMANA_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@dataclass
class ScriptConfig:
    name: str
    path: str
    enabled: bool = True
    interval_minutes: int = 60
    schedule_type: str = "interval"
    cron_time: str = "09:00"
    active_hours_start: str = "08:00"
    active_hours_end: str = "22:00"
    active_days: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])
    timeout: int = 300

    @property
    def full_path(self) -> Path:
        p = Path(self.path)
        if not p.is_absolute():
            p = SCRIPTS_DIR / self.path
        return p.resolve()

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> ScriptConfig:
        return ScriptConfig(**{k: v for k, v in d.items() if k in ScriptConfig.__dataclass_fields__})


@dataclass
class AppConfig:
    scripts: list[ScriptConfig] = field(default_factory=list)
    pause: bool = False
    post_run_rpcs: list[str] = field(default_factory=lambda: [
        "fn_atualizar_minigrafico",
        "fn_refresh_ranking_fiis",
        "fn_limpar_b3_historico",
    ])

    def to_dict(self) -> dict:
        return {
            "pause": self.pause,
            "post_run_rpcs": self.post_run_rpcs,
            "scripts": [s.to_dict() for s in self.scripts],
        }

    @staticmethod
    def from_dict(d: dict) -> AppConfig:
        return AppConfig(
            pause=d.get("pause", False),
            post_run_rpcs=d.get("post_run_rpcs", []),
            scripts=[ScriptConfig.from_dict(s) for s in d.get("scripts", [])],
        )


class Repository:
    def __init__(self):
        self._path = CONFIG_PATH
        self.config = AppConfig()

    def load(self) -> AppConfig:
        if self._path.exists():
            try:
                with open(self._path, encoding="utf-8") as f:
                    data = json.load(f)
                self.config = AppConfig.from_dict(data)
                self._migrate_days()
            except (json.JSONDecodeError, KeyError) as e:
                print(f"[Repository] Erro ao ler config: {e}. Usando padrao.")
                self.config = AppConfig()
        else:
            self.config = self._default_config()
            self.save()
        return self.config

    def _migrate_days(self):
        changed = False
        for sc in self.config.scripts:
            if not sc.active_days:
                continue
            d = sorted(sc.active_days)
            if d == [1, 2, 3, 4, 5]:
                sc.active_days = [0, 1, 2, 3, 4]
                changed = True
            elif d == [1, 2, 3, 4, 5, 6]:
                sc.active_days = [0, 1, 2, 3, 4, 5]
                changed = True
            elif d == [0, 1, 2, 3, 4, 5, 6]:
                pass
        if changed:
            self.save()

    def save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.config.to_dict(), f, indent=2, ensure_ascii=False)
        tmp.replace(self._path)

    def get_script(self, name: str) -> Optional[ScriptConfig]:
        for s in self.config.scripts:
            if s.name == name:
                return s
        return None

    def add_script(self, script: ScriptConfig):
        existing = self.get_script(script.name)
        if existing:
            idx = self.config.scripts.index(existing)
            self.config.scripts[idx] = script
        else:
            self.config.scripts.append(script)
        self.save()

    def remove_script(self, name: str):
        self.config.scripts = [s for s in self.config.scripts if s.name != name]
        self.save()

    def _default_config(self) -> AppConfig:
        defaults = [
            ScriptConfig("B3_COTACOES", "../data-updates/atualizar_b3_cotacoes_aovivo.py",
                         interval_minutes=10, active_hours_start="09:00", active_hours_end="18:00",
                         active_days=[0, 1, 2, 3, 4], timeout=300),
            ScriptConfig("FNET_DADOS", "../data-updates/atualizar_fnet_dados.py",
                         interval_minutes=10, active_hours_start="09:00", active_hours_end="18:00",
                         active_days=[0, 1, 2, 3, 4], timeout=300),
            ScriptConfig("FNET_RENDIMENTOS", "../data-updates/atualizar_fnet_rendimentos.py",
                         interval_minutes=60, active_hours_start="09:00", active_hours_end="18:00",
                         active_days=[0, 1, 2, 3, 4], timeout=120),
            ScriptConfig("YOUTUBE", "../data-updates/atualizar_youtube_videos.py",
                         interval_minutes=60, timeout=300),
            ScriptConfig("B3_COTAHIST", "../data-updates/gdrive_cotahist.py",
                         interval_minutes=60, active_days=[0, 1, 2, 3, 4], timeout=300),
            ScriptConfig("CVM_FII", "../data-updates/atualizar_cvm_fii_mensal.py",
                         interval_minutes=120, active_days=[0, 1, 2, 3, 4, 5], timeout=300),
            ScriptConfig("CVM_FIAGRO", "../data-updates/atualizar_cvm_fiagro_mensal.py",
                         interval_minutes=120, active_days=[0, 1, 2, 3, 4, 5], timeout=300),
            ScriptConfig("CVM_CADASTRAL", "../data-updates/atualizar_cvm_cadastral.py",
                         interval_minutes=120, active_days=[0, 1, 2, 3, 4, 5], timeout=300),
            ScriptConfig("STATUS_ACOES", "../data-updates/atualizar_statusinvest_acoes.py",
                         interval_minutes=120, active_days=[0, 1, 2, 3, 4, 5], timeout=300),
            ScriptConfig("STATUS_DIVIDENDOS", "../data-updates/atualizar_statusinvest_dividendos.py",
                         interval_minutes=120, active_days=[0, 1, 2, 3, 4, 5], timeout=300),
            ScriptConfig("FATOS_IA", "../data-updates/processar_fatos_ia.py",
                         interval_minutes=120, timeout=300),
        ]
        return AppConfig(scripts=defaults)
