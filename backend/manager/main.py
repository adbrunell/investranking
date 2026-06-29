"""
Invest Ranking - Gerenciador de Scripts
Interface Grafica (PyQt6) + Agendamento (APScheduler) + Execucao (QProcess)
Minimiza para a bandeja do sistema ao fechar/minimizar.
"""

import sys
from pathlib import Path

# Garantir que o diretorio do projeto esteja no path
_PROJECT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from app.models import Repository
from app.scheduler import ScriptScheduler
from app.gui import MainWindow, TrayManager, make_app_icon


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Invest Ranking - Gerenciador")
    app.setWindowIcon(make_app_icon())
    app.setQuitOnLastWindowClosed(False)

    repository = Repository()
    repository.load()

    scheduler = ScriptScheduler()

    window = MainWindow(scheduler, repository)
    tray = TrayManager(window, scheduler)

    window.showMaximized()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
