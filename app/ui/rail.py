"""Colonne « Activités à planifier » : une carte avec jauge par activité."""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QScrollArea,
                               QVBoxLayout, QWidget)

from ..store import fmt_hours
from . import dnd
from .common import Dot, ElidedLabel, Gauge, button, label, repolish


class ActivityCard(QFrame):
    def __init__(self, store, act, parent=None):
        super().__init__(parent)
        self.act_id = act.id
        self._press: QPoint | None = None
        self.setObjectName("ActCard")
        total, done = store.total_blocks(act), store.placed_count(act.id)
        self.full = done >= total
        _, line = store.colors(act)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 9, 10, 9)
        lay.setSpacing(0)
        top = QHBoxLayout()
        top.setSpacing(7)
        top.addWidget(Dot(line, 9))
        name = ElidedLabel(act.name)
        name.setStyleSheet("font-weight: 600; font-size: 13px; background: transparent;")
        top.addWidget(name, 1)
        top.addWidget(label("⋮⋮", color="#8a98a8"))
        lay.addLayout(top)
        person = label(store.name(act.person_id) or "Intervenant à définir", size=12, muted=True)
        person.setContentsMargins(16, 1, 0, 7)
        lay.addWidget(person)
        gauge = Gauge()
        gauge.set_values(total, done)
        lay.addWidget(gauge)
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 5, 0, 0)
        bottom.addWidget(label(f"{fmt_hours(done * store.block_hours)} / {fmt_hours(act.hours)} placées",
                               size=11, muted=True))
        bottom.addStretch(1)
        bottom.addWidget(label("Complet" if self.full else f"reste {fmt_hours(store.remaining_hours(act))}",
                               size=11, bold=True, color="#1d7a43" if self.full else "#a16207"))
        lay.addLayout(bottom)

        if self.full:
            eff = QGraphicsOpacityEffect(self)
            eff.setOpacity(0.6)
            self.setGraphicsEffect(eff)
            self.setToolTip("Toutes les heures de cette activité sont placées.")
        else:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.setToolTip(f"Glissez sur un créneau pour poser un bloc de {fmt_hours(store.block_hours)}.")

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and not self.full:
            self._press = e.position().toPoint()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if (self._press is not None and e.buttons() & Qt.MouseButton.LeftButton
                and (e.position().toPoint() - self._press).manhattanLength() >= QApplication.startDragDistance()):
            self._press = None
            dnd.start_drag(self, "new", self.act_id)
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._press = None
        super().mouseReleaseEvent(e)


class ActivityRail(QFrame):
    """Déposer un bloc du planning ici le retire (sa jauge redevient jaune)."""
    add_requested = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setObjectName("Rail")
        self.setFixedWidth(268)
        self.setAcceptDrops(True)
        self.setProperty("dropHover", False)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 12, 14)
        lay.setSpacing(8)
        head = QHBoxLayout()
        head.setSpacing(6)
        head.addWidget(label("Activités à planifier", size=14, bold=True))
        self.count = label(muted=True)
        head.addWidget(self.count)
        head.addStretch(1)
        lay.addLayout(head)
        lay.addWidget(label("Glissez une activité sur un créneau pour poser un bloc. "
                            "Glissez un bloc ici pour le retirer.", size=12, muted=True, wrap=True))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list = QWidget()
        self.list.setObjectName("Transparent")
        self.list_lay = QVBoxLayout(self.list)
        self.list_lay.setContentsMargins(0, 0, 2, 0)
        self.list_lay.setSpacing(8)
        self.list_lay.addStretch(1)
        scroll.setWidget(self.list)
        scroll.viewport().setStyleSheet("background: transparent;")
        lay.addWidget(scroll, 1)

        add = button("+  Nouvelle activité", "dashed")
        add.clicked.connect(self.add_requested)
        lay.addWidget(add)

        store.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        while self.list_lay.count() > 1:
            item = self.list_lay.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.deleteLater()
        for act in self.store.activities:
            self.list_lay.insertWidget(self.list_lay.count() - 1, ActivityCard(self.store, act))
        left = sum(self.store.remaining_hours(a) for a in self.store.activities)
        self.count.setText(f"· {fmt_hours(left)} à placer")

    def _set_hover(self, on: bool) -> None:
        if self.property("dropHover") != on:
            self.setProperty("dropHover", on)
            repolish(self)

    def dragEnterEvent(self, e):
        data = dnd.decode(e.mimeData())
        if data and data[0] == "move":
            e.acceptProposedAction()
            self._set_hover(True)

    def dragMoveEvent(self, e):
        data = dnd.decode(e.mimeData())
        if data and data[0] == "move":
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self._set_hover(False)

    def dropEvent(self, e):
        self._set_hover(False)
        data = dnd.decode(e.mimeData())
        if data and data[0] == "move":
            e.acceptProposedAction()
            bid = data[1]
            dnd.on_drop(lambda: self.store.remove_block(bid))
