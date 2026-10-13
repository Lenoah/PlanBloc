"""Glisser-déposer.

La zone de dépôt n'applique pas l'action tout de suite : elle l'enregistre, et la source
l'exécute après la fin du glissement. Ainsi la grille peut être reconstruite sans détruire
le widget qui est encore en train de gérer le glissement.

`hub` annonce le début et la fin d'un glissement : la grille s'en sert pour colorer à
l'avance les cellules (vert / orange / rouge).
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QByteArray, QMimeData, QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QDrag

MIME = "application/x-planificateur"
_pending: Optional[Callable[[], None]] = None


class _Hub(QObject):
    started = Signal(str, str, int)     # type (« new » | « move »), identifiant, partie attrapée
    finished = Signal()


hub = _Hub()


def decode(mime: QMimeData) -> Optional[tuple[str, str, int]]:
    """Retourne (« new » | « move », identifiant, partie attrapée) ou None."""
    if mime is None or not mime.hasFormat(MIME):
        return None
    raw = bytes(mime.data(MIME).data()).decode("utf-8")
    parts = raw.split(":")
    if len(parts) != 3 or not parts[1]:
        return None
    return parts[0], parts[1], int(parts[2])


def on_drop(action: Callable[[], None]) -> None:
    global _pending
    _pending = action


def start_drag(source, kind: str, ident: str, part: int = 0) -> None:
    global _pending
    _pending = None
    mime = QMimeData()
    mime.setData(MIME, QByteArray(f"{kind}:{ident}:{part}".encode("utf-8")))
    drag = QDrag(source)
    drag.setMimeData(mime)
    pm = source.grab()
    drag.setPixmap(pm)
    drag.setHotSpot(QPoint(min(24, pm.width() // 2), pm.height() // 2))
    hub.started.emit(kind, ident, part)
    try:
        drag.exec(Qt.DropAction.MoveAction)
    finally:
        hub.finished.emit()
    action, _pending = _pending, None
    if action:
        QTimer.singleShot(0, action)
