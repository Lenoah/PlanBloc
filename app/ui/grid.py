"""Grille du planning : semaines en colonnes, jours × créneaux en lignes."""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import ( QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QDialog, QRadioButton,QButtonGroup, QToolButton, QVBoxLayout,QGraphicsDropShadowEffect)
from .. import theme
from ..store import VISIBLE_WEEKS
from . import dnd
from .common import ElidedLabel

HEAD_CSS = "background: #f6f8fb; border-bottom: 1px solid #dfe5ec;"
OVERLAY_HINT = "Survolez un nom et appuyez sur D pour voir ses disponibilités."
# Fond des cellules pendant un glisser (aperçu) et sous le calque d'une ressource
PREVIEW_FILL = {"ok": "#e3f6e9", "orange": "#fff1dc", "rouge": "#ffe3e4"}
OVERLAY_FILL = {"libre": "#e3f6e9", "pris": "#fff1dc", "indisponible": "#ffe3e4"}
OVERLAY_LINE = {"libre": "ok", "pris": "orange", "indisponible": "rouge"}


def resource_label(store, rid: str, placeholder: str) -> ElidedLabel:
    """Nom cliquable au survol : le raccourci D affiche les disponibilités de cette ressource."""
    lab = ElidedLabel(store.name(rid) or placeholder)
    lab.setProperty("rid", rid)
    lab.setAttribute(Qt.WidgetAttribute.WA_Hover)
    lab.setObjectName("ResName")
    return lab


class BlockCard(QFrame):
    clicked = Signal(str)
    remove_requested = Signal(str)

    def __init__(self, store, block, part: int, editable: bool, resource_kind: str = "", parent=None):
        super().__init__(parent)
        self.block_id = block.id
        self.person_id = block.person_id
        self.part = part
        self.editable = editable
        self._press: QPoint | None = None
        self.setObjectName("BlockCard")
        chk = store.check(block)
        act = store.activity(block.activity_id)
        fill, line = store.colors(act)
        # La couleur de la matière reste toujours ; un problème ajoute un cadre orange / rouge et ⚠.
        warn = editable and chk.is_conflict
        if warn:
            border = f"2px solid {theme.STATUS[chk.status]['border']}"
        elif editable and chk.status == "incomplet":
            border = "1px dashed #8a98a8"
        else:
            border = "1px solid transparent"
        self.setStyleSheet(
            f"#BlockCard {{ background: {fill}; border: {border}; border-left: 4px solid {line}; border-radius: 5px; }}"
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
        if block.span > 1:
            tag = QLabel(f"{part + 1}/{block.span}")
            tag.setStyleSheet("color: #4a5a6b; font-size: 10px;")
            tag.setToolTip(f"Séance de {block.span} créneaux consécutifs")
            top.addWidget(tag)
        self.close_btn = QToolButton()
        self.close_btn.setText("✕")
        self.close_btn.setFixedSize(18, 18)
        self.close_btn.setToolTip("Retirer cette séance du planning")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet("QToolButton { background: #ffffff; border: none; border-radius: 4px; font-size: 10px; }"
                                     "QToolButton:hover { background: #ffe9ea; color: #c92a2a; }")
        self.close_btn.hide()
        self.close_btn.clicked.connect(lambda: self.remove_requested.emit(self.block_id))
        top.addWidget(self.close_btn)
        lay.addLayout(top)

        sub = QHBoxLayout()
        sub.setSpacing(3)
        if resource_kind == "personne":
            names = [resource_label(store, block.room_id, "Local à choisir")]
        elif resource_kind in ("local", "materiel"):
            names = [resource_label(store, block.person_id, "Intervenant à choisir")]
        else:
            names = [resource_label(store, block.room_id, "Local ?"),
                     resource_label(store, block.person_id, "Intervenant ?")]
        for i, n in enumerate(names):
            n.setStyleSheet("QLabel { font-size: 11px; color: #4a5a6b; } QLabel:hover { color: #2563eb; }")
            if i:
                dot = QLabel("·")
                dot.setStyleSheet("font-size: 11px; color: #4a5a6b;")
                sub.addWidget(dot)
            sub.addWidget(n, 1)
        lay.addLayout(sub)

        tip = list(chk.lines) if editable else []
        tip.append(OVERLAY_HINT)
        self.setToolTip("\n".join(tip))
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
            dnd.start_drag(self, "move", self.block_id, self.part)
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._press is not None:
            self._press = None
            if self.editable:
                self.clicked.emit(self.block_id)
            return
        super().mouseReleaseEvent(e)


class Cell(QFrame):
    dropped = Signal(str, str, int, int, int, int)   # type, identifiant, partie, semaine, jour, créneau
    drag_hover = Signal(object, bool)                # cellule, entrée / sortie

    def __init__(self, editable: bool, first_row: bool, parent=None):
        super().__init__(parent)
        self.editable, self.first_row = editable, first_row
        self.week = self.day = self.slot = 0
        self.mode = "ouvert"            # ouvert | hors | conge | vide (au-delà de la dernière semaine)
        self.unavailable = False
        self.preview: str | None = None
        self.overlay: str | None = None
        self.hover = False
        self.cards: list[BlockCard] = []
        self.setMinimumSize(110, 52)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(4, 4, 4, 4)
        self.lay.setSpacing(3)
        self.note = QLabel()
        self.note.setStyleSheet("color: #6b7a8b; font-size: 11px; font-style: italic; background: transparent;")
        self.note.setWordWrap(True)
        self.note.hide()
        self.lay.addWidget(self.note)
        self.lay.addStretch(1)

    def configure(self, week: int, day: int, slot: int, mode: str, unavailable: bool, note: str = "") -> None:
        self.week, self.day, self.slot = week, day, slot
        self.mode, self.unavailable = mode, unavailable
        self.setAcceptDrops(self.editable and mode == "ouvert")
        self.set_note(note)
        self.update()

    def set_note(self, text: str) -> None:
        self.note.setText(text)
        self.note.setVisible(bool(text))

    def set_preview(self, status: str | None) -> None:
        if status != self.preview:
            self.preview = status
            self.update()

    def set_hover(self, on: bool) -> None:
        if on != self.hover:
            self.hover = on
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
            self.drag_hover.emit(self, True)

    def dragMoveEvent(self, e):
        if dnd.decode(e.mimeData()):
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self.drag_hover.emit(self, False)

    def dropEvent(self, e):
        self.drag_hover.emit(self, False)
        data = dnd.decode(e.mimeData())
        if data:
            e.acceptProposedAction()
            self.dropped.emit(data[0], data[1], data[2], self.week, self.day, self.slot)

    def paintEvent(self, e):
        p = QPainter(self)
        r = self.rect()
        hatch = QBrush(QColor("#d9dfe7"), Qt.BrushStyle.BDiagPattern)
        if self.mode == "vide":
            p.fillRect(r, QColor("#f6f8fb"))
        elif self.mode == "hors":
            p.fillRect(r, QColor("#f3f5f8"))
        elif self.mode == "conge":
            p.fillRect(r, QColor("#f1f3f6"))
            p.fillRect(r, hatch)
        elif self.preview:
            p.fillRect(r, QColor(PREVIEW_FILL[self.preview]))
        elif self.overlay:
            p.fillRect(r, QColor(OVERLAY_FILL[self.overlay]))
            if self.overlay == "indisponible":
                p.fillRect(r, QBrush(QColor("#f3b3b5"), Qt.BrushStyle.BDiagPattern))
        elif self.unavailable:
            p.fillRect(r, QColor("#f1f3f6"))
            p.fillRect(r, hatch)
        else:
            p.fillRect(r, QColor("#ffffff"))
        p.setPen(QColor(theme.LINE_DAY if self.first_row else theme.LINE_SOFT))
        p.drawLine(r.topLeft(), r.topRight())
        p.setPen(QColor(theme.LINE_SOFT))
        p.drawLine(r.topLeft(), r.bottomLeft())
        if self.preview and self.mode == "ouvert":
            p.setPen(QPen(QColor(theme.STATUS[self.preview]["border"]), 1))
            p.drawRect(r.adjusted(1, 1, -2, -2))
        if self.hover:
            p.setPen(QPen(QColor(theme.ACCENT), 3))
            p.drawRect(r.adjusted(1, 1, -2, -2))
            

class PlacementDialog(QDialog):
    def __init__(self, nom_cours, jour, horaire, parent=None):
        super().__init__(parent)

        # Je prépare ma fenêtre.
        self.setWindowTitle("Planifier une séance")
        self.setFixedWidth(480)
        self.setObjectName("PlacementDialog")
        self.choix = "une_fois"

        self.setStyleSheet("""
            QDialog#PlacementDialog {
                background-color: #ffffff;
            }
            QLabel {
                background: transparent;
                color: #1e293b;
            }
            QPushButton {
                border: none;
                border-radius: 9px;
                padding: 12px 18px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton#CancelButton {
                background-color: #eef2f7;
                color: #475569;
            }
            QPushButton#CancelButton:hover {
                background-color: #e2e8f0;
            }
            QPushButton#ConfirmButton {
                background-color: #315edb;
                color: white;
            }
            QPushButton#ConfirmButton:hover {
                background-color: #244fc0;
            }
            QPushButton#ChoiceCard {
                text-align: left;
                border: 2px solid #e0e6ef;
                border-radius: 12px;
                background-color: white;
                color: #1e293b;
                padding: 15px;
                font-size: 13px;
            }
            QPushButton#ChoiceCard:checked {
                background-color: #eef3ff;
                border: 2px solid #4468e9;
            }
            QPushButton#ChoiceCard:hover {
                border: 2px solid #92aaf5;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Je crée l'en-tête bleu foncé.
        header = QFrame()
        header.setStyleSheet(
            "background-color: #182b50;"
        )

        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(26, 24, 26, 25)
        header_layout.setSpacing(8)

        icone = QLabel("▦")
        icone.setStyleSheet(
            "color: #ffffff; font-size: 28px;"
        )
        header_layout.addWidget(icone)

        titre = QLabel("Planifier une séance")
        titre.setStyleSheet(
            "color: white; font-size: 21px; font-weight: 700;"
        )
        header_layout.addWidget(titre)

        sous_titre = QLabel(
            "Personnalisez la fréquence de votre cours"
        )
        sous_titre.setStyleSheet(
            "color: #c8d5e9; font-size: 12px;"
        )
        header_layout.addWidget(sous_titre)

        layout.addWidget(header)

        # Je crée le contenu principal.
        contenu = QFrame()
        contenu.setStyleSheet(
            "QFrame { background-color: white; }"
        )

        corps = QVBoxLayout(contenu)
        corps.setContentsMargins(26, 24, 26, 25)
        corps.setSpacing(14)

        # Je crée une carte avec les informations du cours.
        info = QFrame()
        info.setObjectName("CourseInfo")
        info.setStyleSheet("""
            QFrame#CourseInfo {
                background-color: #f3f6fb;
                border-radius: 12px;
            }
        """)

        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(16, 15, 16, 15)
        info_layout.setSpacing(9)

        nom = QLabel("📘  " + nom_cours)
        nom.setWordWrap(True)
        nom.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #172b4d;"
        )
        info_layout.addWidget(nom)

        horaire_label = QLabel(
            f"📅  {jour}          ◷  {horaire}"
        )
        horaire_label.setStyleSheet(
            "font-size: 12px; color: #64748b;"
        )
        info_layout.addWidget(horaire_label)

        corps.addWidget(info)

        # Je crée le titre de la sélection.
        label = QLabel("Fréquence du cours")
        label.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #172b4d;"
        )
        corps.addWidget(label)

        # Je crée deux cartes sélectionnables.
        self.option_unique = QPushButton(
            "◉   Une seule séance\n"
            "       Uniquement la semaine sélectionnée"
        )
        self.option_unique.setObjectName("ChoiceCard")
        self.option_unique.setCheckable(True)
        self.option_unique.setChecked(True)
        self.option_unique.setMinimumHeight(78)

        self.option_repetition = QPushButton(
            "◷   Chaque semaine\n"
            "       Même jour et même horaire"
        )
        self.option_repetition.setObjectName("ChoiceCard")
        self.option_repetition.setCheckable(True)
        self.option_repetition.setMinimumHeight(78)

        # Je permets de sélectionner un seul choix.
        groupe = QButtonGroup(self)
        groupe.setExclusive(True)
        groupe.addButton(self.option_unique)
        groupe.addButton(self.option_repetition)

        corps.addWidget(self.option_unique)
        corps.addWidget(self.option_repetition)

        # Je crée les boutons du bas.
        boutons = QHBoxLayout()
        boutons.setSpacing(10)

        annuler = QPushButton("Annuler")
        annuler.setObjectName("CancelButton")
        annuler.clicked.connect(self.reject)

        confirmer = QPushButton("Confirmer  →")
        confirmer.setObjectName("ConfirmButton")
        confirmer.clicked.connect(self.valider)
        confirmer.setDefault(True)

        boutons.addStretch()
        boutons.addWidget(annuler)
        boutons.addWidget(confirmer)

        corps.addSpacing(10)
        corps.addLayout(boutons)

        layout.addWidget(contenu)

    def valider(self):
        # Je récupère le choix de l'utilisateur.
        if self.option_repetition.isChecked():
            self.choix = "repetition"
        else:
            self.choix = "une_fois"

        self.accept()

  



class PlanningGrid(QFrame):
    """editable=True : onglet Planning. editable=False : vue d'une ressource (consultation seule)."""
    block_clicked = Signal(str)

    def __init__(self, store, editable: bool = True, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.store, self.editable = store, editable
        # Je garde le niveau de zoom du planning.
        self.zoom = 1.0
        self.resource_id: str | None = None
        self.overlay_id: str | None = None
        self._drag: tuple[str, str, int, int] | None = None     # type, identifiant, partie, nb créneaux
        self._shape = None
        self.cells: dict[tuple[int, int, int], Cell] = {}
        self.heads: list[QLabel] = []
        self.corner: QLabel | None = None
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(1, 1, 1, 1)
        self.grid.setSpacing(0)
        store.changed.connect(self.refresh)
        store.offset_changed.connect(self.refresh)
        if editable:
            dnd.hub.started.connect(self._drag_started)
            dnd.hub.finished.connect(self._drag_finished)
        self.refresh()

    def set_resource(self, rid: str | None) -> None:
        self.resource_id = rid
        self.refresh()

    def set_overlay(self, rid: str | None) -> None:
        self.overlay_id = rid
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
        st = self.store
        ns = len(st.slots)
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
        for d, wd in enumerate(st.days):
            tint, line = theme.DAY_TINTS[wd % len(theme.DAY_TINTS)]
            day = QLabel(st.day_name(d))
            day.setFixedWidth(84)
            day.setStyleSheet(f"background: {tint}; border-left: 4px solid {line}; border-top: 1px solid {theme.LINE_DAY};"
                              "padding-left: 7px; font-weight: 600; font-size: 12px;")
            self.grid.addWidget(day, 1 + d * ns, 0, ns, 1)
            for s, sl in enumerate(st.slots):
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
                    # Je règle la taille des cases selon le zoom.
                    cell.setMinimumSize(
                    round(110 * self.zoom),
                    round(52 * self.zoom)
                    )
                    cell.dropped.connect(self._on_drop)
                    cell.drag_hover.connect(self._on_hover)
                    self.grid.addWidget(cell, row, 2 + ci)
                    self.cells[(d, s, ci)] = cell
        for ci in range(VISIBLE_WEEKS):
            self.grid.setColumnStretch(2 + ci, 1)

    def _visible_blocks(self, w: int, d: int, s: int):
        st = self.store
        blocks = st.blocks_at(w, d, s)
        if self.editable:
            return [b for b in blocks if st.filiere_of(b) == st.filiere_id]
        rid = self.resource_id
        return [b for b in blocks if rid and rid in (b.person_id, b.room_id, b.material_id)]

    def _overlay_state(self, w: int, d: int, s: int) -> tuple[str, str]:
        st, rid = self.store, self.overlay_id
        if st.is_unavailable(rid, w, d, s):
            return "indisponible", "Indisponible"
        other = st.used_by(rid, w, d, s)
        if other:
            fil = st.filiere_of(other)
            if fil == st.filiere_id:        # la séance est déjà visible dans la case
                return "pris", ""
            return "pris", f"Pris · {st.activity_name(other.activity_id)} ({st.filieres.get(fil, '?')})"
        return "libre", ""

    def refresh(self) -> None:
        st = self.store
        shape = (tuple(st.days), tuple(s.id for s in st.slots))
        self.setUpdatesEnabled(False)
        try:
            if shape != self._shape:
                self._build()
                self._shape = shape
            rid = self.resource_id
            self.corner.setText(st.name(rid) if (not self.editable and rid) else "Jour / Créneau")
            last_day = len(st.days) - 1
            for ci, h in enumerate(self.heads):
                w = st.offset + ci
                if w < st.weeks:
                    h.setText(f"<b>Semaine {w + 1}</b><br><span style='color:#5b6b7c; font-size:11px'>"
                              f"{st.date_of(w, 0):%d/%m} – {st.date_of(w, last_day):%d/%m}</span>")
                else:
                    h.setText("")
            for (d, s, ci), cell in self.cells.items():
                w = st.offset + ci
                cell.clear_cards()
                cell.overlay = None
                cell.preview = None
                if w >= st.weeks:
                    cell.configure(w, d, s, "vide", False)
                    continue
                mode = st.day_state(w, d)
                note = st.holidays.get(st.date_of(w, d), "") if mode == "conge" else ""
                unav = bool(mode == "ouvert" and not self.editable and rid and st.is_unavailable(rid, w, d, s))
                if unav:
                    note = "Indisponible"
                if mode == "ouvert" and self.editable and self.overlay_id:
                    cell.overlay, note = self._overlay_state(w, d, s)
                cell.configure(w, d, s, mode, unav, note)
                for b in self._visible_blocks(w, d, s):
                    kind = st.kind_of(rid) if not self.editable and rid else ""
                    card = BlockCard(st, b, s - st.pos(b)[2], self.editable, kind)
                    if self.editable:
                        card.clicked.connect(self.block_clicked)
                        card.remove_requested.connect(self._remove)
                    cell.add_card(card)
        finally:
            self.setUpdatesEnabled(True)

    # ------------------------------------------------------------------ aperçu pendant le glisser
    def _drag_started(self, kind: str, ident: str, part: int) -> None:
        st = self.store
        if not self.isVisible():
            return
        if kind == "new":
            act = st.activity(ident)
            span = st.session_span(act) if act else 1
        else:
            b = st.block(ident)
            span = b.span if b else 1
        self._drag = (kind, ident, part, max(1, span))
        for (d, s, ci), cell in self.cells.items():
            w = st.offset + ci
            cell.set_preview(st.preview(kind, ident, part, w, d, s) if cell.mode == "ouvert" else None)

    def _drag_finished(self) -> None:
        self._drag = None
        for cell in self.cells.values():
            cell.set_preview(None)
            cell.set_hover(False)

    def _on_hover(self, cell: Cell, entered: bool) -> None:
        """Encadre en bleu tous les créneaux que la séance occupera."""
        for c in self.cells.values():
            c.set_hover(False)
        if not entered or not self._drag:
            return
        _, _, part, span = self._drag
        ci = cell.week - self.store.offset
        for i in range(span):
            c = self.cells.get((cell.day, cell.slot - part + i, ci))
            if c:
                c.set_hover(True)
    
    
    
    def _on_drop(self, kind: str, ident: str, part: int, w: int, d: int, s: int) -> None:
        st = self.store
        start = s - part

        if kind == "new":

            def choisir_placement():
                act = st.activity(ident)
                if act is None:
                    return

                # Je vérifie si le cours peut être placé.
                span = st.session_span(act)
                if st.fits(w, d, start, span) is not None:
                    st.place_new(ident, w, d, start)
                    return

                # Je récupère le jour et l'horaire.
                jour = st.day_name(d)
                horaire = st.time_label(start, span)

                # J'ouvre ma nouvelle fenêtre.
                fenetre = PlacementDialog(
                    act.name, jour, horaire, self
                )

                if fenetre.exec() != QDialog.DialogCode.Accepted:
                    return

                # Je place une seule séance.
                if fenetre.choix == "une_fois":
                    st.place_new(ident, w, d, start)

                # Je répète le cours chaque semaine.
                elif fenetre.choix == "repetition":
                    st.place_repeated(ident, w, d, start)

            dnd.on_drop(choisir_placement)

        elif kind == "move":
            # Je conserve le déplacement des cours.
            dnd.on_drop(
                lambda: st.move_block(ident, w, d, start)
            )



    def _remove(self, bid: str) -> None:
        QTimer.singleShot(0, lambda: self.store.remove_block(bid))
    def wheelEvent(self, event):
    # Je zoome seulement si la touche Ctrl est enfoncée.
     if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
        direction = event.angleDelta().y()

        if direction == 0:
            event.accept()
            return

        # Je limite le zoom entre 70 % et 160 %.
        pas = 0.1 if direction > 0 else -0.1
        nouveau_zoom = round(
            max(0.7, min(1.6, self.zoom + pas)), 2
        )

        if nouveau_zoom != self.zoom:
            self.zoom = nouveau_zoom

            # Je redimensionne les cases existantes.
            for cell in self.cells.values():
                cell.setMinimumSize(
                    round(110 * self.zoom),
                    round(52 * self.zoom)
                )

            self.grid.invalidate()
            self.updateGeometry()

        event.accept()
        return

    # Sans Ctrl, je conserve le comportement normal.
     super().wheelEvent(event)
