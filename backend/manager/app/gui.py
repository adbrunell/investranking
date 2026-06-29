from __future__ import annotations
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QTime, QTimer
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QListWidgetItem, QHeaderView,
    QGroupBox, QFormLayout, QLineEdit, QCheckBox, QComboBox,
    QSpinBox, QTimeEdit, QLabel, QSplitter, QPlainTextEdit, QMenu,
    QSystemTrayIcon, QMessageBox, QFileDialog, QFrame, QAbstractItemView,
    QAbstractSpinBox, QDialog, QDialogButtonBox, QScrollArea,
    QTableWidget, QTableWidgetItem,
)

from .models import ScriptConfig, DIAS_SEMANA, Repository
from .scheduler import ScriptScheduler


FONTS = {"mono": QFont("Cascadia Code, Consolas, Courier New", 10)}
C = {
    "bg": "#111318",
    "surface": "#1a1d24",
    "surface2": "#1f232b",
    "border": "#2a2e36",
    "text": "#e2e5e9",
    "muted": "#8a909a",
    "accent": "#ffde59",
    "green": "#4ade80",
    "red": "#f87171",
    "yellow": "#fbbf24",
    "blue": "#60a5fa",
}


def make_app_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(QColor("#111318"))
    p = QPainter(pm)
    p.setPen(QColor("#ffde59"))
    p.setFont(QFont("Segoe UI", 28))
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "IR")
    p.fillRect(0, 56, 64, 8, QColor("#ffde59"))
    p.end()
    return QIcon(pm)


def styled(text: str, color: str = "") -> str:
    c = f"color: {color};" if color else ""
    return f"<span style='{c}'>{text}</span>"


class StatusDot(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(10, 10)
        self._color = C["muted"]
        self._update()

    def set_color(self, color: str):
        self._color = color
        self._update()

    def _update(self):
        self.setStyleSheet(
            f"background: {self._color}; border-radius: 5px; min-width: 10px; min-height: 10px;"
        )


class ScriptListItem(QFrame):
    def __init__(self, name: str, label: str, parent=None):
        super().__init__(parent)
        self.name = name
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        self.dot = StatusDot()
        layout.addWidget(self.dot)

        info = QVBoxLayout()
        info.setSpacing(0)
        title = QLabel(label)
        title.setStyleSheet(f"color: {C['text']}; font-size: 13px; font-weight: 600;")
        self.sub = QLabel(name)
        self.sub.setStyleSheet(f"color: {C['muted']}; font-size: 11px;")
        info.addWidget(title)
        info.addWidget(self.sub)
        layout.addLayout(info, 1)

        self._label = title
        self._label_text = label

    def set_status(self, status: str):
        colors = {"running": C["blue"], "ok": C["green"], "error": C["red"]}
        self.dot.set_color(colors.get(status, C["muted"]))

    def set_subtitle(self, text: str):
        self.sub.setText(text)


class MainWindow(QMainWindow):
    SORT_ORDER = [
        "B3_COTACOES", "FNET_DADOS", "FNET_RENDIMENTOS",
        "YOUTUBE", "B3_COTAHIST",
        "CVM_FII", "CVM_FIAGRO", "CVM_CADASTRAL",
        "STATUS_ACOES", "STATUS_DIVIDENDOS",
        "FATOS_IA",
    ]
    DIAS_ABREV = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]

    def __init__(self, scheduler: ScriptScheduler, repository: Repository):
        super().__init__()
        self._scheduler = scheduler
        self._repo = repository
        self._script_status: dict[str, str] = {}
        self._items: dict[str, int] = {}  # name -> table row

        self._log_buffer: list[str] = []
        self._log_timer = QTimer(self)
        self._log_timer.setSingleShot(True)
        self._log_timer.timeout.connect(self._flush_log)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_table)

        self._setup_ui()
        self._connect_signals()
        self._load_scripts()

        self._refresh_timer.start(2000)

        self.setWindowTitle("Invest Ranking - Gerenciador")
        self.resize(1100, 720)
        self._apply_theme()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        toolbar = self._build_toolbar()
        main_layout.addWidget(toolbar)

        # === TABELA ===
        self._table = QTableWidget()
        self._table.setColumnCount(9)
        self._table.setHorizontalHeaderLabels(["", "Ativo", "Nome", "Repetir", "Dias", "Horario", "Ultima", "Proxima", ""])
        hh = self._table.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._table.setColumnWidth(0, 16)
        self._table.setColumnWidth(1, 40)
        self._table.setColumnWidth(3, 120)
        self._table.setColumnWidth(4, 160)
        self._table.setColumnWidth(5, 100)
        self._table.setColumnWidth(6, 120)
        self._table.setColumnWidth(7, 120)
        self._table.setColumnWidth(8, 50)
        hh.setStretchLastSection(False)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._table.itemSelectionChanged.connect(self._on_table_select)

        main_layout.addWidget(self._table, 2)

        # === EDITOR COMPACTO ===
        self._detail_bar = QWidget()
        self._detail_bar.setStyleSheet(f"""
            QWidget {{ background: {C['surface']}; border-top: 1px solid {C['border']}; }}
        """)
        detail_lay = QVBoxLayout(self._detail_bar)
        detail_lay.setContentsMargins(12, 6, 12, 6)
        detail_lay.setSpacing(4)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self._cfg_name = QLineEdit()
        self._cfg_name.setPlaceholderText("Nome")
        self._cfg_name.setFixedWidth(160)
        self._cfg_path = QLineEdit()
        self._cfg_path.setPlaceholderText("caminho/script.py")
        browse = QPushButton("...")
        browse.setFixedWidth(28)
        browse.clicked.connect(self._browse_script)
        self._cfg_enabled = QCheckBox("Ativo")
        row1.addWidget(QLabel("Nome:"))
        row1.addWidget(self._cfg_name)
        row1.addWidget(QLabel("Arquivo:"))
        row1.addWidget(self._cfg_path, 1)
        row1.addWidget(browse)
        row1.addWidget(self._cfg_enabled)

        self._cfg_rec_type = QComboBox()
        self._cfg_rec_type.addItems(["A cada X min", "Todo dia as"])
        self._cfg_rec_type.currentIndexChanged.connect(self._on_rec_changed)
        self._cfg_interval = QSpinBox()
        self._cfg_interval.setRange(1, 1440)
        self._cfg_interval.setValue(60)
        self._cfg_interval.setSuffix(" min")
        self._cfg_interval.setFixedWidth(90)
        self._cfg_rec_time = QTimeEdit()
        self._cfg_rec_time.setDisplayFormat("HH:mm")
        self._cfg_rec_time.setTime(QTime(9, 0))
        self._cfg_rec_time.setFixedWidth(70)
        self._cfg_rec_time.hide()
        row1.addWidget(QLabel("Repetir:"))
        row1.addWidget(self._cfg_rec_type)
        row1.addWidget(self._cfg_interval)
        row1.addWidget(self._cfg_rec_time)
        row1.addStretch()
        detail_lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(6)
        self._cfg_days = []
        for label in self.DIAS_ABREV:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setFixedHeight(24)
            btn.setStyleSheet(f"""
                QPushButton {{ font-size: 10px; padding: 1px 8px;
                    background: {C['surface2']}; color: {C['muted']};
                    border: 1px solid {C['border']}; border-radius: 3px; }}
                QPushButton:checked {{ background: {C['accent']}; color: #111;
                    border-color: {C['accent']}; font-weight: 600; }}
                QPushButton:hover {{ background: {C['border']}; }}
            """)
            self._cfg_days.append(btn)
            row2.addWidget(btn)
        for text, fn in [("Todos", self._days_all), ("Uteis", self._days_weekdays), ("Nenhum", self._days_none)]:
            sbtn = QPushButton(text)
            sbtn.setFixedHeight(20)
            sbtn.setStyleSheet(f"QPushButton {{ font-size: 9px; padding: 0 6px; background: transparent; color: {C['muted']}; border: 1px solid {C['border']}; border-radius: 3px; }} QPushButton:hover {{ background: {C['surface2']}; }}")
            sbtn.clicked.connect(fn)
            row2.addWidget(sbtn)

        row2.addSpacing(12)
        self._cfg_limit_hours = QCheckBox("Horario")
        self._cfg_limit_hours.toggled.connect(self._on_limit_changed)
        row2.addWidget(self._cfg_limit_hours)
        self._cfg_hours_start = QTimeEdit()
        self._cfg_hours_start.setDisplayFormat("HH:mm")
        self._cfg_hours_start.setTime(QTime(9, 0))
        self._cfg_hours_start.setFixedWidth(60)
        row2.addWidget(self._cfg_hours_start)
        row2.addWidget(QLabel("as"))
        self._cfg_hours_end = QTimeEdit()
        self._cfg_hours_end.setDisplayFormat("HH:mm")
        self._cfg_hours_end.setTime(QTime(18, 0))
        self._cfg_hours_end.setFixedWidth(60)
        row2.addWidget(self._cfg_hours_end)

        row2.addSpacing(12)
        row2.addWidget(QLabel("Timeout:"))
        self._cfg_timeout = QSpinBox()
        self._cfg_timeout.setRange(10, 600)
        self._cfg_timeout.setValue(300)
        self._cfg_timeout.setSuffix("s")
        self._cfg_timeout.setFixedWidth(80)
        row2.addWidget(self._cfg_timeout)

        self._btn_save = QPushButton("Salvar")
        self._btn_save.setFixedHeight(24)
        self._btn_save.setStyleSheet(f"QPushButton {{ background: {C['accent']}; color: #111; font-weight: 600; border: none; border-radius: 4px; padding: 4px 14px; font-size: 12px; }} QPushButton:hover {{ opacity: 0.8; }}")
        self._btn_save.clicked.connect(self._save_config)
        self._btn_run = QPushButton("▶")
        self._btn_run.setFixedSize(28, 24)
        self._btn_run.setStyleSheet(f"QPushButton {{ color: {C['green']}; border: 1px solid {C['green']}; border-radius: 4px; font-size: 12px; background: transparent; }} QPushButton:hover {{ background: rgba(74,222,128,0.1); }}")
        self._btn_run.clicked.connect(self._run_selected)
        row2.addWidget(self._btn_save)
        row2.addWidget(self._btn_run)
        row2.addStretch()
        detail_lay.addLayout(row2)

        self._detail_bar.hide()
        main_layout.addWidget(self._detail_bar)

        # === LOG ===
        log_group = QGroupBox("Log")
        log_group.setStyleSheet(f"QGroupBox {{ color: {C['muted']}; font-size: 12px; border: none; padding: 4px 0 0 0; }}")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(12, 2, 12, 6)

        log_tb = QHBoxLayout()
        self._log_clear = QPushButton("Limpar")
        self._log_clear.setFixedSize(70, 22)
        self._log_clear.setStyleSheet(f"QPushButton {{ background: {C['surface2']}; color: {C['text']}; border: 1px solid {C['border']}; border-radius: 4px; font-size: 11px; padding: 2px 8px; }}")
        self._log_clear.clicked.connect(self._clear_log)
        log_tb.addStretch()
        log_tb.addWidget(self._log_clear)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(FONTS["mono"])
        self._log.setMaximumBlockCount(500)
        self._log.setFixedHeight(160)

        log_layout.addLayout(log_tb)
        log_layout.addWidget(self._log)
        main_layout.addWidget(log_group)

    def _build_toolbar(self):
        tb = QFrame()
        tb.setStyleSheet(f"""
            QFrame {{ background: {C['surface']}; border-bottom: 1px solid {C['border']}; }}
            QPushButton {{ background: {C['surface2']}; color: {C['text']};
                border: 1px solid {C['border']}; border-radius: 6px;
                padding: 6px 16px; font-size: 13px; }}
            QPushButton:hover {{ background: {C['border']}; }}
            QPushButton#btnPause {{ color: {C['yellow']}; }}
            QPushButton#btnPause.paused {{ color: {C['green']}; }}
        """)
        lay = QHBoxLayout(tb)
        lay.setContentsMargins(12, 6, 12, 6)

        self._btn_add = QPushButton("+ Adicionar")
        self._btn_remove = QPushButton("- Remover")
        self._btn_run_all = QPushButton("▶ Executar Todos")
        self._btn_pause = QPushButton("⏸ Pausar")
        self._btn_pause.setObjectName("btnPause")
        self._pause_label = QLabel("")
        self._pause_label.setStyleSheet(f"color: {C['muted']}; font-size: 12px;")

        self._btn_add.clicked.connect(self._add_script_dialog)
        self._btn_remove.clicked.connect(self._remove_script)
        self._btn_run_all.clicked.connect(self._run_all)
        self._btn_pause.clicked.connect(self._toggle_pause)

        lay.addWidget(self._btn_add)
        lay.addWidget(self._btn_remove)
        lay.addSpacing(16)
        lay.addWidget(self._btn_run_all)
        lay.addWidget(self._btn_pause)
        lay.addWidget(self._pause_label)
        lay.addStretch()

        return tb

    def _connect_signals(self):
        self._scheduler.log_line.connect(self._on_log)
        self._scheduler.script_status.connect(self._on_status)

    def _load_scripts(self):
        config = self._repo.config
        scripts = sorted(config.scripts, key=lambda s: self._sort_key(s.name))
        self._items.clear()
        self._table.setRowCount(0)

        for sc in scripts:
            self._add_table_row(sc)

        self._scheduler.load_config(config)
        self._scheduler.start()

        if scripts:
            self._table.selectRow(0)

    def _add_table_row(self, sc: ScriptConfig):
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setRowHeight(row, 28)

        dot = QLabel("●")
        dot.setStyleSheet(f"color: {C['muted']}; font-size: 10px;")
        dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setCellWidget(row, 0, dot)

        cb = QCheckBox()
        cb.setChecked(sc.enabled)
        cb.stateChanged.connect(lambda state, n=sc.name: self._toggle_enabled(n, state))
        self._table.setCellWidget(row, 1, cb)

        n = QTableWidgetItem(sc.name)
        n.setToolTip(f"Caminho: {sc.path}")
        self._table.setItem(row, 2, n)

        rec_text = f"A cada {sc.interval_minutes}min" if sc.schedule_type == "interval" else f"Todo dia {sc.cron_time}"
        self._table.setItem(row, 3, QTableWidgetItem(rec_text))

        if sc.active_days:
            days_text = self._days_text(sc.active_days)
        else:
            days_text = "Nunca"
        self._table.setItem(row, 4, QTableWidgetItem(days_text))

        if sc.active_hours_start != "00:00" or sc.active_hours_end != "23:59":
            hours_text = f"{sc.active_hours_start}-{sc.active_hours_end}"
        else:
            hours_text = "24h"
        self._table.setItem(row, 5, QTableWidgetItem(hours_text))

        last_run = self._scheduler.get_last_run(sc.name)
        last_text = last_run.strftime("%H:%M %d/%m/%Y") if last_run else "-"
        self._table.setItem(row, 6, QTableWidgetItem(last_text))

        next_run = self._scheduler.get_next_run(sc.name)
        next_text = next_run.strftime("%H:%M %d/%m/%Y") if next_run else "-"
        self._table.setItem(row, 7, QTableWidgetItem(next_text))

        run_btn = QPushButton("▶")
        run_btn.setFixedSize(26, 22)
        run_btn.setStyleSheet(f"QPushButton {{ color: {C['green']}; border: 1px solid {C['green']}; border-radius: 3px; font-size: 11px; background: transparent; }} QPushButton:hover {{ background: rgba(74,222,128,0.15); }} QPushButton:disabled {{ color: {C['border']}; border-color: {C['border']}; }}")
        run_btn.clicked.connect(lambda checked, n=sc.name: self._scheduler.run_now(n))
        self._table.setCellWidget(row, 8, run_btn)

        self._items[sc.name] = row

    def _days_text(self, days: list[int]) -> str:
        if set(days) == {0, 1, 2, 3, 4, 5, 6}:
            return "Todos os dias"
        if days == [0, 1, 2, 3, 4]:
            return "Seg a Sex"
        names = [self.DIAS_ABREV[d] for d in sorted(days)]
        return ", ".join(names)

    def _toggle_enabled(self, name: str, state):
        sc = self._repo.get_script(name)
        if sc:
            sc.enabled = bool(state)
            self._repo.save()
            self._scheduler.update_script(sc)

    def _sort_key(self, name: str) -> int:
        try:
            return self.SORT_ORDER.index(name)
        except ValueError:
            return 999

    def _on_table_select(self):
        rows = self._table.selectedItems()
        if not rows:
            self._detail_bar.hide()
            self._current_editing = None
            return
        row = rows[0].row()
        name_item = self._table.item(row, 2)
        if not name_item:
            self._detail_bar.hide()
            return
        name = name_item.text()
        sc = self._repo.get_script(name)
        if not sc:
            return
        self._detail_bar.show()
        self._populate_form(sc)

    def _populate_form(self, sc: ScriptConfig):
        self._current_editing = sc.name
        self._cfg_name.setText(sc.name)
        self._cfg_path.setText(sc.path)
        self._cfg_enabled.setChecked(sc.enabled)
        self._cfg_interval.setValue(sc.interval_minutes)

        if sc.schedule_type == "cron":
            self._cfg_rec_type.setCurrentIndex(1)
            self._cfg_rec_time.setTime(QTime.fromString(sc.cron_time, "HH:mm"))
        else:
            self._cfg_rec_type.setCurrentIndex(0)

        for i, btn in enumerate(self._cfg_days):
            btn.setChecked(i in sc.active_days)

        has_hours = sc.active_hours_start != "00:00" or sc.active_hours_end != "23:59"
        self._cfg_limit_hours.setChecked(has_hours)
        if has_hours:
            self._cfg_hours_start.setTime(QTime.fromString(sc.active_hours_start, "HH:mm"))
            self._cfg_hours_end.setTime(QTime.fromString(sc.active_hours_end, "HH:mm"))
        else:
            self._cfg_hours_start.setTime(QTime(9, 0))
            self._cfg_hours_end.setTime(QTime(18, 0))

        self._cfg_timeout.setValue(sc.timeout)
        self._on_rec_changed()
        self._on_limit_changed(has_hours)
        status = self._script_status.get(sc.name, "idle")
        self._refresh_run_btn(status)

    def _refresh_run_btn(self, status: str):
        is_run = status != "running"
        self._btn_run.setEnabled(is_run)
        self._btn_run.setText("⏳" if not is_run else "▶")

    def _save_config(self):
        name = self._cfg_name.text().strip()
        if not name:
            return

        active_days_list = [i for i in range(7) if self._cfg_days[i].isChecked()]
        if not active_days_list:
            active_days_list = [0, 1, 2, 3, 4, 5, 6]

        if self._cfg_limit_hours.isChecked():
            h_start = self._cfg_hours_start.time().toString("HH:mm")
            h_end = self._cfg_hours_end.time().toString("HH:mm")
        else:
            h_start = "00:00"
            h_end = "23:59"

        sc = ScriptConfig(
            name=name,
            path=self._cfg_path.text().strip(),
            enabled=self._cfg_enabled.isChecked(),
            interval_minutes=self._cfg_interval.value(),
            schedule_type="cron" if self._cfg_rec_type.currentIndex() == 1 else "interval",
            cron_time=self._cfg_rec_time.time().toString("HH:mm"),
            active_hours_start=h_start,
            active_hours_end=h_end,
            active_days=active_days_list,
            timeout=self._cfg_timeout.value(),
        )

        self._repo.add_script(sc)

        old_sc = self._scheduler._configs.get(sc.name)
        if old_sc:
            self._scheduler.update_script(sc)
        else:
            self._scheduler.add_script(sc)

        # Update table row
        if sc.name in self._items:
            row = self._items[sc.name]
            self._table.item(row, 2).setText(sc.name)
            self._table.item(row, 3).setText(f"A cada {sc.interval_minutes}min" if sc.schedule_type == "interval" else f"Todo dia {sc.cron_time}")
            self._table.item(row, 4).setText(self._days_text(sc.active_days))
            h = f"{sc.active_hours_start}-{sc.active_hours_end}" if (sc.active_hours_start != "00:00" or sc.active_hours_end != "23:59") else "24h"
            self._table.item(row, 5).setText(h)
        else:
            self._add_table_row(sc)

        self._log_message("INFO", name, "Configuracao salva")

    def _browse_script(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar Script Python", str(Path.home()), "Python (*.py)"
        )
        if path:
            try:
                rel = Path(path).relative_to(
                    Path(__file__).resolve().parent.parent.parent / "data-updates"
                )
                self._cfg_path.setText(str(rel))
            except ValueError:
                self._cfg_path.setText(path)

    def _add_script_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Novo Script")
        dialog.setStyleSheet(f"QDialog {{ background: {C['bg']}; }}")
        dialog.setFixedSize(400, 180)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        name_input = QLineEdit()
        name_input.setPlaceholderText("Ex: MEU_SCRIPT")
        form.addRow("Nome:", name_input)
        path_input = QLineEdit()
        path_input.setPlaceholderText("caminho/relativo/para/script.py")
        browse_btn = QPushButton("...")
        browse_btn.setFixedWidth(30)
        browse_btn.clicked.connect(lambda: path_input.setText(
            QFileDialog.getOpenFileName(dialog, "Selecionar", str(Path.home()), "Python (*.py)")[0]
        ))
        path_row = QHBoxLayout()
        path_row.addWidget(path_input, 1)
        path_row.addWidget(browse_btn)
        form.addRow("Arquivo:", path_row)
        layout.addLayout(form)
        layout.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = name_input.text().strip()
            path = path_input.text().strip()
            if name and path:
                sc = ScriptConfig(name=name, path=path)
                self._repo.add_script(sc)
                self._scheduler.add_script(sc)
                self._add_table_row(sc)
                for r in range(self._table.rowCount()):
                    if self._table.item(r, 2) and self._table.item(r, 2).text() == name:
                        self._table.selectRow(r)
                        break

    def _remove_script(self):
        rows = self._table.selectedItems()
        if not rows:
            return
        row = rows[0].row()
        name = self._table.item(row, 2).text()
        reply = QMessageBox.question(self, "Remover", f"Remover script '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.No:
            return
        self._scheduler.remove_script(name)
        self._repo.remove_script(name)
        self._items.pop(name, None)
        self._table.removeRow(row)
        self._detail_bar.hide()
        self._current_editing = None

    def _run_all(self):
        for name in self._items:
            self._scheduler.run_now(name)

    def _run_selected(self):
        if self._current_editing:
            self._scheduler.run_now(self._current_editing)

    def _toggle_pause(self):
        if self._scheduler.is_paused:
            self._scheduler.resume()
            self._btn_pause.setText("⏸ Pausar")
            self._btn_pause.setProperty("class", "")
            self._pause_label.setText("")
        else:
            self._scheduler.pause()
            self._btn_pause.setText("▶ Retomar")
            self._btn_pause.setProperty("class", "paused")
            self._pause_label.setText("Pausado")
        self._btn_pause.style().unpolish(self._btn_pause)
        self._btn_pause.style().polish(self._btn_pause)

    def _on_rec_changed(self):
        is_interval = self._cfg_rec_type.currentIndex() == 0
        self._cfg_interval.setVisible(is_interval)
        self._cfg_rec_time.setVisible(not is_interval)

    def _on_limit_changed(self, checked: bool):
        self._cfg_hours_start.setEnabled(checked)
        self._cfg_hours_end.setEnabled(checked)

    def _days_all(self):
        for btn in self._cfg_days:
            btn.setChecked(True)

    def _days_weekdays(self):
        for i, btn in enumerate(self._cfg_days):
            btn.setChecked(i < 5)

    def _days_none(self):
        for btn in self._cfg_days:
            btn.setChecked(False)

    def _on_log(self, level: str | None, name: str, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        color = {"RUN": C["blue"], "OK": C["green"], "ERRO": C["red"],
            "WARN": C["yellow"], "INFO": C["muted"]}.get(level or "INFO", C["text"])
        prefix = f"[{name}]" if level is None else f"[{level}] [{name}]"
        html = (f"<span style='color:{C['muted']}'>{ts}</span> "
                f"<span style='color:{color}'>{prefix}</span> "
                f"<span style='color:{C['text']}'>{message}</span>")
        self._log_buffer.append(html)
        if not self._log_timer.isActive():
            self._log_timer.start(50)

    def _flush_log(self):
        if self._log_buffer:
            self._log.appendHtml("\n".join(self._log_buffer))
            self._log_buffer.clear()
            sb = self._log.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _log_message(self, level: str, name: str, message: str):
        self._on_log(level, name, message)

    def _clear_log(self):
        self._log.clear()

    def _on_status(self, name: str, status: str):
        self._script_status[name] = status
        if name == self._current_editing:
            self._refresh_run_btn(status)
        self._refresh_table_row_status(name)

    def _refresh_table_row_status(self, name: str):
        row = self._items.get(name)
        if row is None:
            return
        status = self._script_status.get(name, "idle")
        dot = self._table.cellWidget(row, 0)
        colors = {"running": C["blue"], "ok": C["green"], "error": C["red"]}
        dot.setStyleSheet(f"color: {colors.get(status, C['muted'])}; font-size: 10px;")

    def _refresh_table(self):
        for name, row in list(self._items.items()):
            if row >= self._table.rowCount():
                continue
            s = self._scheduler.get_status(name)
            if s == "running":
                self._refresh_table_row_status(name)
            nr = self._scheduler.get_next_run(name)
            if nr:
                self._table.item(row, 7).setText(nr.strftime("%H:%M %d/%m/%Y"))

    def _apply_theme(self):
        self.setStyleSheet(f"""
            QMainWindow {{ background: {C['bg']}; }}
            QWidget {{ color: {C['text']}; font-family: 'Segoe UI', sans-serif; font-size: 13px; }}
            QTableWidget {{
                background: {C['surface']}; border: none; gridline-color: transparent;
                selection-background-color: {C['surface2']};
                alternate-background-color: #191c23;
            }}
            QTableWidget::item {{
                padding: 2px 6px; border: none; font-size: 12px;
            }}
            QTableWidget::item:selected {{
                background: {C['surface2']}; color: {C['accent']};
            }}
            QHeaderView::section {{
                background: {C['bg']}; color: {C['muted']};
                border: none; border-bottom: 1px solid {C['border']};
                padding: 4px 6px; font-size: 11px; font-weight: 600;
            }}
            QCheckBox {{ spacing: 4px; }}
            QComboBox {{
                background: {C['surface2']}; color: {C['text']};
                border: 1px solid {C['border']}; border-radius: 3px;
                padding: 2px 6px; font-size: 12px;
            }}
            QComboBox::drop-down {{ border: none; width: 16px; }}
            QSpinBox, QTimeEdit {{
                background: {C['surface2']}; color: {C['text']};
                border: 1px solid {C['border']}; border-radius: 3px;
                padding: 2px 4px; font-size: 12px;
            }}
            QSpinBox::up-button, QSpinBox::down-button,
            QTimeEdit::up-button, QTimeEdit::down-button {{
                width: 0px; border: none; background: transparent;
            }}
            QLineEdit {{
                background: {C['surface2']}; color: {C['text']};
                border: 1px solid {C['border']}; border-radius: 3px;
                padding: 2px 6px; font-size: 12px;
            }}
            QScrollBar:vertical {{
                background: {C['bg']}; width: 6px; border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {C['border']}; border-radius: 3px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QPlainTextEdit {{
                background: {C['surface']}; color: {C['text']};
                border: 1px solid {C['border']}; border-radius: 4px;
                padding: 6px; font-size: 12px; font-family: {FONTS['mono'].family()};
            }}
        """)

    def closeEvent(self, event):
        event.ignore()
        self.hide()

    def changeEvent(self, event):
        if event.type() == event.Type.WindowStateChange:
            if self.windowState() & Qt.WindowState.WindowMinimized:
                event.ignore()
                self.hide()
                return
        super().changeEvent(event)


class TrayManager:
    def __init__(self, window: MainWindow, scheduler: ScriptScheduler):
        self._window = window
        self._scheduler = scheduler
        self._tray = QSystemTrayIcon(make_app_icon(), window)
        self._tray.setToolTip("Invest Ranking - Gerenciador")
        self._build_menu()
        self._tray.activated.connect(self._on_activated)
        self._tray.show()

    def _build_menu(self):
        menu = QMenu()

        show_action = QAction("Abrir Painel", self._window)
        show_action.triggered.connect(self._show_window)
        menu.addAction(show_action)

        self._pause_action = QAction("Pausar", self._window)
        self._pause_action.triggered.connect(self._toggle_pause)
        menu.addAction(self._pause_action)

        menu.addSeparator()

        quit_action = QAction("Sair", self._window)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)

    def _show_window(self):
        self._window.showNormal()
        self._window.activateWindow()
        self._window.raise_()

    def _toggle_pause(self):
        if self._scheduler.is_paused:
            self._scheduler.resume()
            self._pause_action.setText("Pausar")
        else:
            self._scheduler.pause()
            self._pause_action.setText("Retomar")

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_window()

    def _quit(self):
        self._tray.hide()
        self._scheduler.shutdown()
        QApplication.quit()
