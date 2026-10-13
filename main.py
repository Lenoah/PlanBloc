"""Point d'entrée : python main.py"""
import sys
from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from app import theme
from app.main_window import APP_NAME, MainWindow
from app.store import Store


def base_dir() -> Path:
    # Exécutable PyInstaller : le dossier data/ est à côté du .exe
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setPalette(theme.light_palette())
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(theme.QSS)

    store = Store()
    reports = store.load_folder(base_dir() / "data")
    win = MainWindow(store)
    win.show()
    bad = [r for r in reports if not r.ok]
    if bad:
        win.go_settings()
        QMessageBox.warning(win, "Fichiers invalides",
                            "Certains fichiers n'ont pas pu être chargés :\n\n" + "\n\n".join(r.detail for r in bad)
                            + "\n\nCorrigez-les ou importez un autre dossier depuis Paramètres.")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
