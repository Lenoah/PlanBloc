"""Glisser-déposer.

La zone de dépôt n'applique pas l'action tout de suite : elle l'enregistre, et la source
l'exécute après la fin du glissement. Ainsi la grille peut être reconstruite sans détruire
le widget qui est encore en train de gérer le glissement.
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QByteArray, QMimeData, QPoint, Qt, QTimer
from PySide6.QtGui import QDrag

MIME = "application/x-planificateur"
_pending: Optional[Callable[[], None]] = None


def decode(mime: QMimeData) -> Optional[tuple[str, str]]:
    """Retourne (« new » | « move », identifiant) ou None."""
    if mime is None or not mime.hasFormat(MIME):
        return None
    raw = bytes(mime.data(MIME).data()).decode("utf-8")
    kind, _, ident = raw.partition(":")
    return (kind, ident) if ident else None


def on_drop(action: Callable[[], None]) -> None:
    global _pending
    _pending = action


def start_drag(source, kind: str, ident: str) -> None:
    global _pending
    _pending = None
    mime = QMimeData()
    mime.setData(MIME, QByteArray(f"{kind}:{ident}".encode("utf-8")))
    drag = QDrag(source)
    drag.setMimeData(mime)
    pm = source.grab()
    drag.setPixmap(pm)
    drag.setHotSpot(QPoint(min(24, pm.width() // 2), pm.height() // 2))
    drag.exec(Qt.DropAction.MoveAction)
    action, _pending = _pending, None
    if action:
        QTimer.singleShot(0, action)
