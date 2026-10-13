"""Contenu des onglets."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QComboBox, QFileDialog, QFrame,
                               QGridLayout, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
                               QScrollArea, QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

from .. import theme
from ..store import DAY_NAMES, DataError, fmt_hours
from .common import Dot, ElidedLabel, Gauge, WeekNav, button, dot_icon, label, separator
from .grid import BlockCard, PlanningGrid
from .rail import ActivityRail


def _scroll(widget: QWidget) -> QScrollArea:
    s = QScrollArea()
    s.setWidgetResizable(True)
    s.setFrameShape(QFrame.Shape.NoFrame)
    s.setWidget(widget)
    s.viewport().setStyleSheet("background: transparent;")
    return s


def _context_bar() -> tuple[QFrame, QHBoxLayout]:
    bar = QFrame()
    bar.setObjectName("ContextBar")
    lay = QHBoxLayout(bar)
    lay.setContentsMargins(16, 8, 16, 8)
    lay.setSpacing(12)
    return bar, lay


def _grid_holder(grid: QWidget) -> QScrollArea:
    holder = QWidget()
    holder.setObjectName("Transparent")
    hl = QVBoxLayout(holder)
    hl.setContentsMargins(14, 12, 14, 14)
    hl.addWidget(grid, 1)
    return _scroll(holder)


class PlanningPage(QWidget):
    block_requested = Signal(str)
    add_requested = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar, bl = _context_bar()
        bl.addWidget(label("Filière", muted=True))
        self.filiere = QComboBox()
        self.filiere.setMinimumWidth(220)
        self.filiere.currentIndexChanged.connect(self._filiere_chosen)
        bl.addWidget(self.filiere)
        bl.addWidget(separator())
        self.dot = Dot(theme.STATUS["ok"]["border"], 9)
        bl.addWidget(self.dot)
        self.msg = ElidedLabel("")
        self.msg.setStyleSheet("color: #33414f; background: transparent;")
        bl.addWidget(self.msg, 1)

        # Calque des disponibilités d'une ressource (raccourci D)
        self.overlay_chip = QFrame()
        self.overlay_chip.setObjectName("OverlayChip")
        cl = QHBoxLayout(self.overlay_chip)
        cl.setContentsMargins(10, 3, 4, 3)
        cl.setSpacing(6)
        self.overlay_lab = QLabel()
        cl.addWidget(self.overlay_lab)
        close = QToolButton()
        close.setText("✕")
        close.setToolTip("Fermer le calque (Échap)")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(lambda: self.set_overlay(None))
        cl.addWidget(close)
        self.overlay_chip.hide()
        bl.addWidget(self.overlay_chip)
        bl.addWidget(WeekNav(store))
        lay.addWidget(bar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        rail = ActivityRail(store)
        rail.add_requested.connect(self.add_requested)
        body.addWidget(rail)
        self.grid = PlanningGrid(store, editable=True)
        self.grid.block_clicked.connect(self.block_requested)
        body.addWidget(_grid_holder(self.grid), 1)
        lay.addLayout(body, 1)

        QShortcut(QKeySequence("D"), self, activated=self._toggle_overlay)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=lambda: self.set_overlay(None))

        store.message.connect(self.show_message)
        store.changed.connect(self._refresh_filiere)
        self._refresh_filiere()

    def _refresh_filiere(self) -> None:
        st = self.store
        items = list(st.filieres.items())
        if [(self.filiere.itemData(i), self.filiere.itemText(i)) for i in range(self.filiere.count())] != items:
            self.filiere.blockSignals(True)
            self.filiere.clear()
            for fid, name in items:
                self.filiere.addItem(name, fid)
            self.filiere.blockSignals(False)
        idx = self.filiere.findData(st.filiere_id)
        if idx >= 0 and idx != self.filiere.currentIndex():
            self.filiere.blockSignals(True)
            self.filiere.setCurrentIndex(idx)
            self.filiere.blockSignals(False)

    def _filiere_chosen(self, _i: int) -> None:
        fid = self.filiere.currentData()
        if fid:
            self.store.set_filiere(fid)

    def _toggle_overlay(self) -> None:
        """Ressource sous le curseur : le nom survolé, sinon l'intervenant de la séance survolée."""
        w, rid = QApplication.widgetAt(QCursor.pos()), None
        while w is not None:
            if w.property("rid") is not None:
                rid = w.property("rid")
                break
            if isinstance(w, BlockCard):
                rid = w.person_id
                break
            w = w.parentWidget()
        if not rid:
            self.show_message("incomplet", "Placez le curseur sur le nom d'un intervenant ou d'un local dans une "
                                           "séance, puis appuyez sur D.")
            return
        self.set_overlay(None if rid == self.grid.overlay_id else rid)

    def set_overlay(self, rid: str | None) -> None:
        self.grid.set_overlay(rid)
        if rid:
            self.overlay_lab.setText(f"Disponibilités : <b>{self.store.name(rid)}</b>")
            self.overlay_chip.setToolTip("Vert : libre · Orange : déjà pris · Rouge : indisponible. Échap pour fermer.")
            self.overlay_chip.setFixedWidth(self.overlay_chip.sizeHint().width())
        self.overlay_chip.setVisible(bool(rid))

    def show_message(self, kind: str, text: str) -> None:
        self.dot.set_color(theme.STATUS.get(kind, theme.STATUS["incomplet"])["border"])
        self.msg.setFullText(text)
        self.msg.setToolTip(text)


class ActivitiesView(QWidget):
    add_requested = Signal()
    HEADERS = ("Activité", "Filière", "Intervenant", "Local habituel", "Durée", "Séance", "Blocs placés",
               "Reste à placer")

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)
        top = QHBoxLayout()
        self.summary = label(color="#4a5a6b")
        top.addWidget(self.summary)
        top.addStretch(1)
        add = button("+  Nouvelle activité", "success")
        add.clicked.connect(self.add_requested)
        top.addWidget(add)
        lay.addLayout(top)
        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setShowGrid(False)
        hh = self.table.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        R = QHeaderView.ResizeMode
        for i, mode in enumerate((R.Stretch, R.ResizeToContents, R.ResizeToContents, R.ResizeToContents,
                                  R.ResizeToContents, R.ResizeToContents, R.Stretch, R.ResizeToContents)):
            hh.setSectionResizeMode(i, mode)
        lay.addWidget(self.table, 1)
        store.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        st = self.store
        order = {fid: i for i, fid in enumerate(st.filieres)}
        acts = sorted(st.activities, key=lambda a: order.get(a.filiere_id, 99))
        self.summary.setText(f"{len(st.filieres)} filières · {len(acts)} activités · "
                             f"créneaux de {fmt_hours(st.block_hours)}")
        self.table.setRowCount(len(acts))
        for row, a in enumerate(acts):
            _, line = st.colors(a)
            name = QTableWidgetItem(dot_icon(line), a.name)
            f = name.font(); f.setBold(True); name.setFont(f)
            self.table.setItem(row, 0, name)
            self.table.setItem(row, 1, QTableWidgetItem(st.filieres.get(a.filiere_id, "—")))
            self.table.setItem(row, 2, QTableWidgetItem(st.name(a.person_id) or "—"))
            self.table.setItem(row, 3, QTableWidgetItem(st.name(a.room_id) or "—"))
            self.table.setItem(row, 4, QTableWidgetItem(fmt_hours(a.hours)))
            self.table.setItem(row, 5, QTableWidgetItem(fmt_hours(a.session_hours)))
            holder = QWidget()
            hl = QHBoxLayout(holder)
            hl.setContentsMargins(8, 0, 12, 0)
            g = Gauge()
            g.set_values(st.total_blocks(a), st.placed_count(a.id))
            hl.addWidget(g)
            self.table.setCellWidget(row, 6, holder)
            left = st.remaining_hours(a)
            text = "Complet" if left <= 0 else f"{fmt_hours(left)} ({st.remaining_blocks(a)} blocs)"
            item = QTableWidgetItem(text)
            item.setForeground(Qt.GlobalColor.darkGreen if left <= 0 else Qt.GlobalColor.darkYellow)
            f = item.font(); f.setBold(True); item.setFont(f)
            self.table.setItem(row, 7, item)


class ResourceView(QWidget):
    """Onglets Personnes / Locaux / Matériels : un sous-onglet par ressource, consultation seule."""

    def __init__(self, store, kind: str, parent=None):
        super().__init__(parent)
        self.store, self.kind = store, kind
        self.selected: str | None = None
        self._ids: list[str] = []
        self.chips: dict[str, QPushButton] = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar, bl = _context_bar()
        chips_box = QWidget()
        chips_box.setObjectName("Transparent")
        self.chips_lay = QHBoxLayout(chips_box)
        self.chips_lay.setContentsMargins(0, 0, 0, 0)
        self.chips_lay.setSpacing(6)
        chip_scroll = QScrollArea()
        chip_scroll.setWidgetResizable(True)
        chip_scroll.setFrameShape(QFrame.Shape.NoFrame)
        chip_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        chip_scroll.setFixedHeight(36)
        chip_scroll.setWidget(chips_box)
        chip_scroll.viewport().setStyleSheet("background: transparent;")
        bl.addWidget(chip_scroll, 1)
        bl.addWidget(label("🔒  Consultation seule · toutes filières", size=12, muted=True))
        bl.addWidget(WeekNav(store))
        lay.addWidget(bar)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.grid = PlanningGrid(store, editable=False)
        lay.addWidget(_grid_holder(self.grid), 1)
        store.changed.connect(self.refresh)
        self.refresh()

    def _select(self, rid: str) -> None:
        self.selected = rid
        self.grid.set_resource(rid)

    def refresh(self) -> None:
        res = self.store.resources[self.kind]
        ids = [r.id for r in res]
        if ids != self._ids:
            for b in self.chips.values():
                self.group.removeButton(b)
                b.deleteLater()
            self.chips.clear()
            while self.chips_lay.count():
                self.chips_lay.takeAt(0)
            for r in res:
                b = QPushButton()
                b.setProperty("chip", True)
                b.setCheckable(True)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.clicked.connect(lambda _c=False, rid=r.id: self._select(rid))
                self.group.addButton(b)
                self.chips_lay.addWidget(b)
                self.chips[r.id] = b
            self.chips_lay.addStretch(1)
            self._ids = ids
        if self.selected not in ids:
            self.selected = ids[0] if ids else None
        for r in res:
            b = self.chips[r.id]
            b.setText(f"{r.name}   {self.store.count_for_resource(r.id)}")
            b.setToolTip(r.owner or "")
            b.setChecked(r.id == self.selected)
        if self.grid.resource_id != self.selected:
            self.grid.set_resource(self.selected)


class ConflictsView(QWidget):
    fix_requested = Signal(str)

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 0)
        lay.setSpacing(10)
        lay.addWidget(label("Cliquez « Corriger » pour changer l'intervenant, le local ou le matériel de la séance. "
                            "Vous pouvez aussi la déplacer dans le planning.", color="#4a5a6b", wrap=True))
        box = QWidget()
        box.setObjectName("Transparent")
        self.list_lay = QVBoxLayout(box)
        self.list_lay.setContentsMargins(0, 0, 8, 18)
        self.list_lay.setSpacing(10)
        lay.addWidget(_scroll(box), 1)
        store.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        while self.list_lay.count():
            item = self.list_lay.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        st = self.store
        conflicts = st.conflicts()
        if not conflicts:
            empty = QLabel("Aucun conflit : toutes les séances placées ont leurs ressources disponibles.")
            empty.setObjectName("Card")
            empty.setStyleSheet("#Card { padding: 22px; color: #4a5a6b; }")
            self.list_lay.addWidget(empty)
        for b in conflicts:
            chk = st.check(b)
            s = theme.STATUS[chk.status]
            card = QFrame()
            card.setObjectName("Conflict")
            card.setStyleSheet(f"#Conflict {{ background: #ffffff; border: 1px solid #dfe5ec; border-left: 5px solid {s['border']};"
                               "border-radius: 10px; } QLabel { background: transparent; border: none; }")
            row = QHBoxLayout(card)
            row.setContentsMargins(16, 13, 16, 13)
            row.setSpacing(14)
            icon = label("⚠", size=20, color=s["border"])
            icon.setAlignment(Qt.AlignmentFlag.AlignTop)
            row.addWidget(icon)
            col = QVBoxLayout()
            col.setSpacing(3)
            head = QHBoxLayout()
            head.setSpacing(10)
            head.addWidget(label(st.activity_name(b.activity_id), size=15, bold=True))
            head.addWidget(label(st.filieres.get(st.filiere_of(b), ""), muted=True))
            head.addWidget(label(st.describe(b), color="#4a5a6b"))
            head.addStretch(1)
            col.addLayout(head)
            for line in chk.lines:
                col.addWidget(label(line, color="#33414f", wrap=True))
            row.addLayout(col, 1)
            fix = button("Corriger", "primary")
            fix.clicked.connect(lambda _c=False, bid=b.id: self.fix_requested.emit(bid))
            row.addWidget(fix, 0, Qt.AlignmentFlag.AlignTop)
            self.list_lay.addWidget(card)
        self.list_lay.addStretch(1)


class SettingsView(QWidget):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        outer = QHBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(16)

        gcard = QFrame()
        gcard.setObjectName("Card")
        gl = QVBoxLayout(gcard)
        gl.setContentsMargins(18, 16, 18, 18)
        gl.setSpacing(12)
        gl.addWidget(label("Calendrier", size=16, bold=True))
        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        form.setColumnStretch(1, 1)
        self.fields: dict[str, QLabel] = {}
        for row, text in enumerate(("Nom", "Période", "Jours", "Créneaux", "Pauses", "Congés")):
            form.addWidget(label(text, color="#4a5a6b"), row, 0, Qt.AlignmentFlag.AlignTop)
            self.fields[text] = label(wrap=True)
            form.addWidget(self.fields[text], row, 1)
        gl.addLayout(form)
        self.info = QLabel()
        self.info.setObjectName("Info")
        self.info.setWordWrap(True)
        gl.addWidget(self.info)
        gl.addStretch(1)
        outer.addWidget(gcard, 1)

        fcard = QFrame()
        fcard.setObjectName("Card")
        fl = QVBoxLayout(fcard)
        fl.setContentsMargins(18, 16, 18, 18)
        fl.setSpacing(10)
        fl.addWidget(label("Fichiers", size=16, bold=True))
        self.folder = label(muted=True, wrap=True)
        fl.addWidget(self.folder)
        self.files_lay = QVBoxLayout()
        self.files_lay.setSpacing(8)
        fl.addLayout(self.files_lay)
        imports = QHBoxLayout()
        imp_dispo = button("Importer un export de disponibilités…")
        imp_dispo.clicked.connect(self._import_dispo)
        imp = button("Importer un dossier…")
        imp.clicked.connect(self._import)
        imports.addWidget(imp_dispo)
        imports.addWidget(imp)
        imports.addStretch(1)
        btns = QHBoxLayout()
        opn = button("Ouvrir un planning…")
        opn.clicked.connect(self._open)
        save_as = button("Enregistrer sous…")
        save_as.clicked.connect(self._save_as)
        save = button("Enregistrer", "primary")
        save.clicked.connect(self._save)
        btns.addWidget(opn)
        btns.addWidget(save_as)
        btns.addStretch(1)
        btns.addWidget(save)
        fl.addSpacing(4)
        fl.addLayout(imports)
        fl.addLayout(btns)
        fl.addStretch(1)
        outer.addWidget(fcard, 1)

        store.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        st, cal = self.store, self.store.cal
        self.fields["Nom"].setText(cal.name or "—")
        self.fields["Période"].setText(f"{cal.start_date:%d/%m/%Y} → {cal.end_date:%d/%m/%Y}  ({st.weeks} semaines)")
        self.fields["Jours"].setText(", ".join(DAY_NAMES[d] for d in st.days))
        self.fields["Créneaux"].setText("   ·   ".join(s.label("–") for s in st.slots))
        self.fields["Pauses"].setText("   ·   ".join(f"{b.name} {b.start:%H:%M}–{b.end:%H:%M}" for b in cal.breaks)
                                      or "—")
        self.fields["Congés"].setText(", ".join(f"{d:%d/%m}" for d in sorted(st.holidays)) or "—")
        self.info.setText(f"Le calendrier vient du fichier du groupe « disponibilités » : il se modifie chez eux, "
                          f"pas ici. Un créneau dure {fmt_hours(st.block_hours)} ; une séance de 4 h occupe "
                          f"{max(1, round(4 / st.block_hours))} créneaux consécutifs du même jour.")
        self.folder.setText(f"Dossier : {st.data_dir}" if st.data_dir else "Aucun dossier chargé.")
        while self.files_lay.count():
            item = self.files_lay.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        for r in st.reports:
            row = QFrame()
            row.setObjectName("FileRow")
            row.setStyleSheet("#FileRow { border: 1px solid #e3e8ee; border-radius: 7px; } QLabel { background: transparent; border: none; }")
            h = QHBoxLayout(row)
            h.setContentsMargins(11, 8, 11, 8)
            col = QVBoxLayout()
            col.setSpacing(1)
            col.addWidget(label(r.name, bold=True))
            col.addWidget(label(f"{r.origin} · {r.detail}", size=12, muted=True, wrap=True))
            h.addLayout(col, 1)
            chip = QLabel("Valide" if r.ok else "Erreur")
            color = theme.STATUS["ok" if r.ok else "rouge"]
            chip.setStyleSheet(f"background: {color['bg']}; color: {color['ink']}; border-radius: 9px; padding: 2px 9px;"
                               "font-size: 12px; font-weight: 600;")
            h.addWidget(chip, 0, Qt.AlignmentFlag.AlignTop)
            self.files_lay.addWidget(row)

    def _warn_bad(self, reports) -> None:
        bad = [r for r in reports if not r.ok]
        if bad:
            QMessageBox.warning(self, "Fichiers invalides", "\n\n".join(r.detail for r in bad))

    def _import_dispo(self) -> None:
        start = str(self.store.data_dir or Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Export du groupe « disponibilités »", start, "JSON (*.json)")
        if not path:
            return
        try:
            self._warn_bad(self.store.import_dispo(Path(path)))
        except OSError as e:
            QMessageBox.critical(self, "Import impossible", str(e))

    def _import(self) -> None:
        start = str(self.store.data_dir or Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Dossier contenant les fichiers JSON", start)
        if folder:
            self._warn_bad(self.store.load_folder(Path(folder)))

    def _open(self) -> None:
        start = str(self.store.data_dir or Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Ouvrir un planning", start, "Planning (*.json)")
        if path:
            try:
                self.store.open_planning(Path(path))
            except DataError as e:
                QMessageBox.warning(self, "Planning invalide", str(e))

    def _save(self) -> None:
        if self.store.planning_path is None:
            self._save_as()
            return
        try:
            self.store.save()
        except OSError as e:
            QMessageBox.critical(self, "Enregistrement impossible", str(e))

    def _save_as(self) -> None:
        start = str(self.store.planning_path or Path.home() / "planning.json")
        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer le planning", start, "Planning (*.json)")
        if path:
            try:
                self.store.save(Path(path))
            except OSError as e:
                QMessageBox.critical(self, "Enregistrement impossible", str(e))
