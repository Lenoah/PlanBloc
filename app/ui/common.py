"""Petits composants réutilisés."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

from .. import theme
from ..store import VISIBLE_WEEKS


def repolish(w: QWidget) -> None:
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


def button(text: str, variant: str | None = None) -> QPushButton:
    b = QPushButton(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if variant:
        b.setProperty("variant", variant)
    return b


def label(text: str = "", *, size: int | None = None, bold: bool = False, muted: bool = False,
          color: str | None = None, wrap: bool = False) -> QLabel:
    lab = QLabel(text)
    css = ["background: transparent"]
    if size:
        css.append(f"font-size: {size}px")
    if bold:
        css.append("font-weight: 600")
    if muted:
        css.append(f"color: {theme.MUTED}")
    if color:
        css.append(f"color: {color}")
    lab.setStyleSheet("; ".join(css))
    lab.setWordWrap(wrap)
    return lab


def dot_icon(color: str, size: int = 12) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(0, 0, size - 1, size - 1)
    p.end()
    return QIcon(pm)


class Dot(QLabel):
    def __init__(self, color: str, size: int = 9, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.set_color(color)

    def set_color(self, color: str) -> None:
        self.setStyleSheet(f"background: {color}; border-radius: {self.width() // 2}px;")


class ElidedLabel(QLabel):
    """Label sur une ligne qui coupe le texte avec « … » s'il manque de place."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full = text
        self.setMinimumWidth(10)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._elide()

    def setFullText(self, text: str) -> None:
        self._full = text
        self._elide()

    def fullText(self) -> str:
        return self._full

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._elide()

    def _elide(self) -> None:
        QLabel.setText(self, self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideRight,
                                                           max(10, self.width())))


class Gauge(QWidget):
    """Jauge d'une activité : un segment par bloc. Gris = placé, jaune = reste à placer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.total, self.done = 1, 0
        self.setFixedHeight(9)
        self.setMinimumWidth(60)

    def set_values(self, total: int, done: int) -> None:
        self.total, self.done = max(1, total), max(0, min(done, total))
        self.setToolTip(f"{self.done} / {self.total} blocs placés")
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        w, h = self.width(), self.height()
        gap = 2 if self.total <= 40 else 1
        seg = (w - gap * (self.total - 1)) / self.total
        if seg < 2:      # trop de blocs : barre continue proportionnelle
            done_w = w * self.done / self.total
            p.setBrush(QColor(theme.GAUGE_DONE)); p.drawRoundedRect(QRectF(0, 0, done_w, h), 2, 2)
            p.setBrush(QColor(theme.GAUGE_LEFT)); p.drawRoundedRect(QRectF(done_w, 0, w - done_w, h), 2, 2)
            return
        x = 0.0
        for i in range(self.total):
            p.setBrush(QColor(theme.GAUGE_DONE if i < self.done else theme.GAUGE_LEFT))
            p.drawRoundedRect(QRectF(x, 0, seg, h), 2, 2)
            x += seg + gap


class WeekNav(QFrame):
    """‹ Semaines 1 – 6 / 12 ›"""

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setObjectName("WeekNav")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.prev, self.next = QPushButton("‹"), QPushButton("›")
        self.lab = QLabel()
        self.lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for b in (self.prev, self.next):
            b.setFixedWidth(34)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prev.setToolTip("Semaines précédentes")
        self.next.setToolTip("Semaines suivantes")
        lay.addWidget(self.prev)
        lay.addWidget(self.lab)
        lay.addWidget(self.next)
        self.prev.clicked.connect(lambda: store.shift_weeks(-1))
        self.next.clicked.connect(lambda: store.shift_weeks(1))
        store.offset_changed.connect(self.refresh)
        store.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        st = self.store
        last = min(st.offset + VISIBLE_WEEKS, st.weeks)
        self.lab.setText(f"Semaines {st.offset + 1} – {last} / {st.weeks}")
        self.prev.setEnabled(st.offset > 0)
        self.next.setEnabled(st.offset + VISIBLE_WEEKS < st.weeks)


def separator() -> QFrame:
    sep = QFrame()
    sep.setFixedSize(1, 22)
    sep.setStyleSheet("background: #e3e8ee;")
    return sep
