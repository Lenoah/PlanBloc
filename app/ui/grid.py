"""Grille du planning : semaines en colonnes, jours × créneaux en lignes."""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QToolButton,
                               QVBoxLayout)

from .. import theme
from ..store import DAY_NAMES, VISIBLE_WEEKS
from . import dnd
from .common import ElidedLabel

HEAD_CSS = "background: #f6f8fb; border-bottom: 1px solid #dfe5ec;"


class BlockCard(QFrame):
    clicked = Signal(str)
    remove_requested = Signal(str)

    def __init__(self, store, block, editable: bool, subtitle: str, parent=None):
        super().__init__(parent)
        self.block_id = block.id
        self.editable = editable
        self._press: QPoint | None = None
        self.setObjectName("BlockCard")
        chk = store.check(block)
        act = store.activity(block.activity_id)
        fill, line = store.colors(act)
        warn = editable and chk.is_conflict
        if warn:
            st = theme.STATUS[chk.status]
            bg, border, left = st["bg"], f"1px solid {st['border']}", st["border"]
        elif editable and chk.status == "incomplet":
            bg, border, left = fill, "1px dashed #8a98a8", line
        else:
            bg, border, left = fill, "1px solid transparent", line
        self.setStyleSheet(
            f"#BlockCard {{ background: {bg}; border: {border}; border-left: 4px solid {left}; border-radius: 5px; }}"
            "QLabel { background: transparent; border: none; }")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 3, 4, 4)
        lay.setSpacing(0)
        top = QHBoxLayout()
        top.setSpacing(4)
        if warn:
            icon = QLabel("⚠")
            icon.setStyleSheet(f"color: {theme.STATUS[chk.status]['border']}; font-weight: 700; font-size: 12px;")
            top.addWidget(icon)
        title = ElidedLabel(act.name if act else "?")
        title.setStyleSheet("font-weight: 600; font-size: 12px;")
        top.addWidget(title, 1)
        self.close_btn = QToolButton()
        self.close_btn.setText("✕")
        self.close_btn.setFixedSize(18, 18)
        self.close_btn.setToolTip("Retirer ce bloc du planning")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet("QToolButton { background: #ffffff; border: none; border-radius: 4px; font-size: 10px; }"
                                     "QToolButton:hover { background: #ffe9ea; color: #c92a2a; }")
        self.close_btn.hide()
        self.close_btn.clicked.connect(lambda: self.remove_requested.emit(self.block_id))
        top.addWidget(self.close_btn)
        lay.addLayout(top)
        sub = ElidedLabel(subtitle)
        sub.setStyleSheet("font-size: 11px; color: #4a5a6b;")
        lay.addWidget(sub)

        self.setToolTip("\n".join(chk.lines))
        self.setMinimumHeight(38)
        if editable:
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def enterEvent(self, e):
        if self.editable:
            self.close_btn.show()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.close_btn.hide()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press = e.position().toPoint()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if (self.editable and self._press is not None and e.buttons() & Qt.MouseButton.LeftButton
                and (e.position().toPoint() - self._press).manhattanLength() >= QApplication.startDragDistance()):
            self._press = None
            self.close_btn.hide()
            dnd.start_drag(self, "move", self.block_id)
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._press is not None:
            self._press = None
            self.clicked.emit(self.block_id)
            return
        super().mouseReleaseEvent(e)


class Cell(QFrame):
    dropped = Signal(str, str, int, int, int)   # type, identifiant, semaine, jour, créneau

    def __init__(self, editable: bool, first_row: bool, parent=None):
        super().__init__(parent)
        self.editable, self.first_row = editable, first_row
        self.week = self.day = self.slot = 0
        self.active, self.unavailable, self._hover = True, False, False
        self.cards: list[BlockCard] = []
        self.setMinimumSize(110, 52)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(4, 4, 4, 4)
        self.lay.setSpacing(3)
        self.unav_label = QLabel("Indisponible")
        self.unav_label.setStyleSheet("color: #8a98a8; font-size: 11px; font-style: italic; background: transparent;")
        self.unav_label.hide()
        self.lay.addWidget(self.unav_label)
        self.lay.addStretch(1)

    def configure(self, week: int, day: int, slot: int, active: bool, unavailable: bool) -> None:
        self.week, self.day, self.slot = week, day, slot
        self.active, self.unavailable = active, unavailable
        self.setAcceptDrops(self.editable and active)
        self.unav_label.setVisible(unavailable)
        self.update()

    def clear_cards(self) -> None:
        for c in self.cards:
            self.lay.removeWidget(c)
            c.hide()
            c.deleteLater()
        self.cards = []

    def add_card(self, card: BlockCard) -> None:
        self.lay.insertWidget(self.lay.count() - 1, card)
        self.cards.append(card)

    def dragEnterEvent(self, e):
        if dnd.decode(e.mimeData()):
            e.acceptProposedAction()
            self._hover = True
            self.update()

    def dragMoveEvent(self, e):
        if dnd.decode(e.mimeData()):
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self._hover = False
        self.update()

    def dropEvent(self, e):
        self._hover = False
        self.update()
        data = dnd.decode(e.mimeData())
        if data:
            e.acceptProposedAction()
            self.dropped.emit(data[0], data[1], self.week, self.day, self.slot)

    def paintEvent(self, e):
        p = QPainter(self)
        r = self.rect()
        if self._hover:
            p.fillRect(r, QColor("#dbe8fb"))
        elif not self.active:
            p.fillRect(r, QColor("#f6f8fb"))
        elif self.unavailable:
            p.fillRect(r, QColor("#f1f3f6"))
            p.fillRect(r, QBrush(QColor("#d9dfe7"), Qt.BrushStyle.BDiagPattern))
        else:
            p.fillRect(r, QColor("#ffffff"))
        p.setPen(QColor(theme.LINE_DAY if self.first_row else theme.LINE_SOFT))
        p.drawLine(r.topLeft(), r.topRight())
        p.setPen(QColor(theme.LINE_SOFT))
        p.drawLine(r.topLeft(), r.bottomLeft())
        if self._hover:
            p.setPen(QPen(QColor(theme.ACCENT), 2))
            p.drawRect(r.adjusted(1, 1, -1, -1))


class PlanningGrid(QFrame):
    """editable=True : onglet Planning. editable=False : vue d'une ressource (consultation seule)."""
    block_clicked = Signal(str)

    def __init__(self, store, editable: bool = True, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.store, self.editable = store, editable
        self.resource_id: str | None = None
        self._shape = None
        self.cells: dict[tuple[int, int, int], Cell] = {}
        self.heads: list[QLabel] = []
        self.corner: QLabel | None = None
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(1, 1, 1, 1)
        self.grid.setSpacing(0)
        store.changed.connect(self.refresh)
        store.offset_changed.connect(self.refresh)
        self.refresh()

    def set_resource(self, rid: str | None) -> None:
        self.resource_id = rid
        self.refresh()

    def _build(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.deleteLater()
        self.cells.clear()
        self.heads.clear()
        g = self.store.grid
        ns = len(g.slots)
        self.corner = QLabel()
        self.corner.setStyleSheet(HEAD_CSS + "padding: 0 12px; font-weight: 600; color: #4a5a6b;")
        self.grid.addWidget(self.corner, 0, 0, 1, 2)
        for ci in range(VISIBLE_WEEKS):
            h = QLabel()
            h.setTextFormat(Qt.TextFormat.RichText)
            h.setAlignment(Qt.AlignmentFlag.AlignCenter)
            h.setStyleSheet(HEAD_CSS + "border-left: 1px solid #e3e8ee; padding: 7px 4px;")
            self.grid.addWidget(h, 0, 2 + ci)
            self.heads.append(h)
        for d in range(g.days):
            tint, line = theme.DAY_TINTS[d % len(theme.DAY_TINTS)]
            day = QLabel(DAY_NAMES[d])
            day.setFixedWidth(84)
            day.setStyleSheet(f"background: {tint}; border-left: 4px solid {line}; border-top: 1px solid {theme.LINE_DAY};"
                              "padding-left: 7px; font-weight: 600; font-size: 12px;")
            self.grid.addWidget(day, 1 + d * ns, 0, ns, 1)
            for s, sl in enumerate(g.slots):
                row = 1 + d * ns + s
                top = theme.LINE_DAY if s == 0 else theme.LINE_SOFT
                t = QLabel(sl.label("–"))
                t.setFixedWidth(96)
                t.setStyleSheet(f"background: #fafbfd; color: #4a5a6b; font-size: 12px; border-top: 1px solid {top};"
                                "padding: 0 8px;")
                self.grid.addWidget(t, row, 1)
                self.grid.setRowStretch(row, 1)
                for ci in range(VISIBLE_WEEKS):
                    cell = Cell(self.editable, first_row=(s == 0))
                    cell.dropped.connect(self._on_drop)
                    self.grid.addWidget(cell, row, 2 + ci)
                    self.cells[(d, s, ci)] = cell
        for ci in range(VISIBLE_WEEKS):
            self.grid.setColumnStretch(2 + ci, 1)

    def _subtitle(self, b) -> str:
        st = self.store
        kind = st.kind_of(self.resource_id) if (not self.editable and self.resource_id) else ""
        if kind == "personne":
            return st.name(b.room_id) or "Local à choisir"
        if kind == "local":
            return st.name(b.person_id) or "Intervenant à choisir"
        parts = [st.name(b.room_id), st.name(b.person_id)]
        return " · ".join(p for p in parts if p) or "Aucune ressource"

    def refresh(self) -> None:
        st, g = self.store, self.store.grid
        shape = (g.days, len(g.slots))
        self.setUpdatesEnabled(False)
        try:
            if shape != self._shape:
                self._build()
                self._shape = shape
            rid = self.resource_id
            self.corner.setText(st.name(rid) if (not self.editable and rid) else "Jour / Créneau")
            for ci, h in enumerate(self.heads):
                w = st.offset + ci
                if w < g.weeks:
                    h.setText(f"<b>Semaine {w + 1}</b><br><span style='color:#5b6b7c; font-size:11px'>"
                              f"{st.date_of(w, 0):%d/%m} – {st.date_of(w, g.days - 1):%d/%m}</span>")
                else:
                    h.setText("")
            for (d, s, ci), cell in self.cells.items():
                w = st.offset + ci
                active = w < g.weeks
                cell.clear_cards()
                unav = bool(active and not self.editable and rid and st.is_unavailable(rid, w, d, s))
                cell.configure(w, d, s, active, unav)
                if not active:
                    continue
                blocks = st.blocks_at(w, d, s)
                if not self.editable:
                    blocks = [b for b in blocks if rid and rid in (b.person_id, b.room_id, b.material_id)]
                for b in blocks:
                    card = BlockCard(st, b, self.editable, self._subtitle(b))
                    if self.editable:
                        card.clicked.connect(self.block_clicked)
                        card.remove_requested.connect(self._remove)
                    cell.add_card(card)
        finally:
            self.setUpdatesEnabled(True)

    def _on_drop(self, kind: str, ident: str, w: int, d: int, s: int) -> None:
        st = self.store
        if kind == "new":
            dnd.on_drop(lambda: st.place_new(ident, w, d, s))
        elif kind == "move":
            dnd.on_drop(lambda: st.move_block(ident, w, d, s))

    def _remove(self, bid: str) -> None:
        QTimer.singleShot(0, lambda: self.store.remove_block(bid))
