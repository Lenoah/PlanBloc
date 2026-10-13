"""Fenêtre principale : barre d'onglets horizontale en haut, le planning prend le reste."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QButtonGroup, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from .ui.dialogs import BlockDialog, ExportDialog, NewActivityDialog
from .ui.pages import ActivitiesView, ConflictsView, PlanningPage, ResourceView, SettingsView

APP_NAME = "Planificateur d'activités"


class TopBar(QFrame):
    tab_selected = Signal(int)
    export_clicked = Signal()

    def __init__(self, labels: list[str], parent=None):
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setFixedHeight(54)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(4)
        logo = QLabel("▦")
        logo.setObjectName("Logo")
        logo.setFixedSize(32, 32)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand = QLabel("Planificateur")
        brand.setObjectName("Brand")
        lay.addWidget(logo)
        lay.addSpacing(6)
        lay.addWidget(brand)
        lay.addSpacing(18)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: list[QPushButton] = []
        self.badge = QLabel()
        self.badge.setObjectName("Badge")
        self.badge.hide()
        for i, text in enumerate(labels):
            b = QPushButton(text)
            b.setProperty("tab", True)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.group.addButton(b, i)
            lay.addWidget(b)
            self.buttons.append(b)
            if text == "Conflits":
                lay.addWidget(self.badge)
                lay.addSpacing(4)
        self.group.idClicked.connect(self.tab_selected)
        lay.addStretch(1)
        export = QPushButton("Exporter PDF")
        export.setObjectName("ExportBtn")
        export.setCursor(Qt.CursorShape.PointingHandCursor)
        export.clicked.connect(self.export_clicked)
        lay.addWidget(export)
        self.buttons[0].setChecked(True)

    def set_badge(self, n: int) -> None:
        self.badge.setText(str(n))
        self.badge.setVisible(n > 0)

    def select(self, index: int) -> None:
        self.buttons[index].setChecked(True)
        self.tab_selected.emit(index)


class MainWindow(QMainWindow):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.resize(1480, 920)
        self.setMinimumSize(1120, 700)

        root = QWidget()
        root.setObjectName("Root")
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self.planning = PlanningPage(store)
        self.activities = ActivitiesView(store)
        self.conflicts = ConflictsView(store)
        self.settings = SettingsView(store)
        pages = [("Planning", self.planning), ("Activités", self.activities),
                 ("Personnes", ResourceView(store, "personne")), ("Locaux", ResourceView(store, "local")),
                 ("Matériels", ResourceView(store, "materiel")), ("Conflits", self.conflicts),
                 ("Paramètres", self.settings)]
        self.topbar = TopBar([p[0] for p in pages])
        v.addWidget(self.topbar)
        self.stack = QStackedWidget()
        for _, w in pages:
            self.stack.addWidget(w)
        v.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.topbar.tab_selected.connect(self.stack.setCurrentIndex)
        self.topbar.export_clicked.connect(self.open_export)
        self.planning.block_requested.connect(self.open_block)
        self.planning.add_requested.connect(self.new_activity)
        self.activities.add_requested.connect(self.new_activity)
        self.conflicts.fix_requested.connect(self.open_block)
        store.changed.connect(self._on_changed)

        save = QShortcut(QKeySequence(QKeySequence.StandardKey.Save), self)
        save.activated.connect(self.save)
        self._on_changed()

    def _on_changed(self) -> None:
        self.topbar.set_badge(len(self.store.conflicts()))
        name = self.store.planning_path.name if self.store.planning_path else "sans titre"
        self.setWindowTitle(f"{APP_NAME} — {name}{' *' if self.store.dirty else ''}")

    def go_settings(self) -> None:
        self.topbar.select(self.stack.indexOf(self.settings))

    def open_block(self, bid: str) -> None:
        QTimer.singleShot(0, lambda: self._show_block(bid))

    def _show_block(self, bid: str) -> None:
        if self.store.block(bid) is not None:
            BlockDialog(self.store, bid, self).open()

    def new_activity(self) -> None:
        if not self.store.resources["personne"]:
            QMessageBox.information(self, APP_NAME, "Importez d'abord les fichiers de disponibilité.")
            return
        NewActivityDialog(self.store, self).open()

    def open_export(self) -> None:
        ExportDialog(self.store, self).open()

    def save(self) -> bool:
        try:
            if self.store.planning_path is None:
                path, _ = QFileDialog.getSaveFileName(self, "Enregistrer le planning",
                                                      str(Path.home() / "planning.json"), "Planning (*.json)")
                if not path:
                    return False
                self.store.save(Path(path))
            else:
                self.store.save()
            return True
        except OSError as e:
            QMessageBox.critical(self, "Enregistrement impossible", str(e))
            return False

    def closeEvent(self, e):
        if not self.store.dirty:
            e.accept()
            return
        B = QMessageBox.StandardButton
        r = QMessageBox.question(self, APP_NAME, "Le planning a été modifié. Enregistrer avant de quitter ?",
                                 B.Save | B.Discard | B.Cancel, B.Save)
        if r == B.Save and self.save():
            e.accept()
        elif r == B.Discard:
            e.accept()
        else:
            e.ignore()
