"""Pop-ups : bloc (ressources / conflit), nouvelle activité, aperçu et export PDF."""
from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPageLayout, QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QSpinBox, QTextBrowser, QVBoxLayout, QWidget)

from .. import theme
from ..store import DAY_NAMES, fmt_hours
from .common import button, label

STATE_COLORS = {"libre": "#1d7a43", "indisponible": "#b42323", "pris": "#a15c00"}


class BlockDialog(QDialog):
    """Clic sur un bloc ou « Corriger » dans Conflits : changer intervenant, local, matériel."""
    FIELDS = (("Intervenant", "personne", "person_id", "— à choisir —"),
              ("Local", "local", "room_id", "— à choisir —"),
              ("Matériel", "materiel", "material_id", "— aucun —"))

    def __init__(self, store, block_id: str, parent=None):
        super().__init__(parent)
        self.store, self.block_id = store, block_id
        self.setWindowTitle("Bloc d'activité")
        self.setMinimumWidth(560)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.header = QFrame()
        self.header.setObjectName("DlgHeader")
        hl = QVBoxLayout(self.header)
        hl.setContentsMargins(20, 16, 20, 14)
        hl.setSpacing(2)
        self.title = label(size=18, bold=True)
        self.when = label(color="#4a5a6b")
        hl.addWidget(self.title)
        hl.addWidget(self.when)
        root.addWidget(self.header)

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(20, 16, 20, 16)
        bl.setSpacing(14)
        self.banner = QLabel()
        self.banner.setWordWrap(True)
        self.banner.setTextFormat(Qt.TextFormat.RichText)
        bl.addWidget(self.banner)
        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setColumnStretch(1, 1)
        self.combos: dict[str, tuple[QComboBox, str, str]] = {}
        for row, (text, kind, field, placeholder) in enumerate(self.FIELDS):
            form.addWidget(label(text, color="#4a5a6b"), row, 0)
            cb = QComboBox()
            cb.setMinimumWidth(340)
            cb.currentIndexChanged.connect(lambda _i, f=field: self._on_change(f))
            form.addWidget(cb, row, 1)
            self.combos[field] = (cb, kind, placeholder)
        bl.addLayout(form)
        bl.addWidget(label("Pour changer de créneau, glissez le bloc ailleurs dans le planning.", size=12, muted=True))
        root.addWidget(body)

        footer = QFrame()
        footer.setObjectName("DlgFooter")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(20, 12, 20, 12)
        remove = button("Retirer ce bloc", "danger")
        remove.clicked.connect(self._remove)
        done = button("Terminé", "primary")
        done.setDefault(True)
        done.clicked.connect(self.accept)
        fl.addWidget(remove)
        fl.addStretch(1)
        fl.addWidget(done)
        root.addWidget(footer)

        self._connected = True
        store.changed.connect(self.refresh)
        self.refresh()

    def done(self, result):
        if self._connected:
            self._connected = False
            try:
                self.store.changed.disconnect(self.refresh)
            except (RuntimeError, TypeError):
                pass
        super().done(result)

    def refresh(self) -> None:
        st = self.store
        b = st.block(self.block_id)
        if b is None:
            self.close()
            return
        act = st.activity(b.activity_id)
        fill, line = st.colors(act)
        self.header.setStyleSheet(f"#DlgHeader {{ background: {fill}; border-top: 5px solid {line}; }}")
        self.title.setText(act.name if act else "?")
        self.when.setText(f"{st.describe(b)}  ({fmt_hours(st.block_hours)})")
        chk = st.check(b)
        s = theme.STATUS[chk.status]
        icon = "✔" if chk.status == "ok" else "⚠"
        self.banner.setText(f"<b>{icon}</b>&nbsp; " + "<br>".join(html.escape(l) for l in chk.lines))
        self.banner.setStyleSheet(f"background: {s['bg']}; border: 1px solid {s['border']}; border-radius: 8px;"
                                  f"padding: 10px 12px; color: {s['ink']};")
        for field, (cb, kind, placeholder) in self.combos.items():
            cb.blockSignals(True)
            cb.clear()
            cb.addItem(placeholder, "")
            for r in st.resources[kind]:
                cb.addItem(st.availability_label(r.id, b), r.id)
                state, _ = st.availability(r.id, b)
                cb.setItemData(cb.count() - 1, QColor(STATE_COLORS[state]), Qt.ItemDataRole.ForegroundRole)
            idx = cb.findData(getattr(b, field))
            cb.setCurrentIndex(idx if idx >= 0 else 0)
            cb.blockSignals(False)

    def _on_change(self, field: str) -> None:
        cb = self.combos[field][0]
        value = cb.currentData() or ""
        store, bid = self.store, self.block_id
        QTimer.singleShot(0, lambda: store.set_block_resource(bid, field, value))

    def _remove(self) -> None:
        store, bid = self.store, self.block_id
        self.close()
        QTimer.singleShot(0, lambda: store.remove_block(bid))


class NewActivityDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Nouvelle activité")
        self.setMinimumWidth(460)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(12)
        lay.addWidget(label("Nouvelle activité", size=18, bold=True))
        lay.addWidget(label(f"Elle sera découpée en blocs de {fmt_hours(store.block_hours)} à placer dans le planning.",
                            muted=True, wrap=True))
        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setColumnStretch(1, 1)
        self.name = QLineEdit()
        self.name.setPlaceholderText("ex. Systèmes d'exploitation")
        self.person = QComboBox()
        for r in store.resources["personne"]:
            self.person.addItem(r.name, r.id)
        self.room = QComboBox()
        for r in store.resources["local"]:
            self.room.addItem(r.name, r.id)
        step = max(1, round(store.block_hours))
        self.hours = QSpinBox()
        self.hours.setRange(step, 400)
        self.hours.setSingleStep(step)
        self.hours.setValue(max(step, 24 - 24 % step))
        self.hours.setSuffix(" h")
        self.blocks_lab = label(muted=True)
        self.hours.valueChanged.connect(self._update_blocks)
        for row, (text, w) in enumerate((("Nom", self.name), ("Intervenant", self.person),
                                         ("Local habituel", self.room), ("Durée totale", self.hours))):
            form.addWidget(label(text, color="#4a5a6b"), row, 0)
            form.addWidget(w, row, 1)
        form.addWidget(self.blocks_lab, 4, 1)
        lay.addLayout(form)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = button("Annuler")
        cancel.clicked.connect(self.reject)
        ok = button("Ajouter", "success")
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addSpacing(6)
        lay.addLayout(row)
        self._update_blocks()

    def _update_blocks(self) -> None:
        import math
        n = math.ceil(self.hours.value() / self.store.block_hours - 1e-9)
        self.blocks_lab.setText(f"= {n} blocs de {fmt_hours(self.store.block_hours)}")

    def _accept(self) -> None:
        name = self.name.text().strip()
        if not name:
            self.name.setFocus()
            self.name.setStyleSheet("border: 1px solid #e03131;")
            return
        self.store.add_activity(name, self.person.currentData() or "", self.room.currentData() or "",
                                self.hours.value())
        self.accept()


def week_html(store, w: int) -> str:
    g = store.grid
    esc = html.escape
    head = "".join(f"<th align='left' bgcolor='#f3f5f8'>{DAY_NAMES[d]} {store.date_of(w, d):%d/%m}</th>"
                   for d in range(g.days))
    rows = []
    for s, sl in enumerate(g.slots):
        cells = []
        for d in range(g.days):
            items = []
            for b in store.blocks_at(w, d, s):
                res = " · ".join(x for x in (store.name(b.room_id), store.name(b.person_id), store.name(b.material_id)) if x)
                items.append(f"<p style='margin:0 0 4px 0'><b>{esc(store.activity_name(b.activity_id))}</b><br>"
                             f"<span style='color:#4a5a6b'>{esc(res)}</span></p>")
            cells.append(f"<td valign='top'>{''.join(items) or '&nbsp;'}</td>")
        rows.append(f"<tr><td valign='top' width='90' style='color:#4a5a6b'>{sl.label('–')}</td>{''.join(cells)}</tr>")
    return (f"<h2 style='margin:0'>Horaire — {esc(store.filiere)}</h2>"
            f"<p style='color:#4a5a6b; margin:2px 0 10px 0'>Semaine {w + 1} · "
            f"{store.date_of(w, 0):%d/%m/%Y} – {store.date_of(w, g.days - 1):%d/%m/%Y}</p>"
            "<table width='100%' border='1' cellspacing='0' cellpadding='6' style='border-collapse:collapse; border-color:#cfd7e0'>"
            f"<tr><th align='left' bgcolor='#f3f5f8'>Créneau</th>{head}</tr>{''.join(rows)}</table>"
            "<p style='color:#8a98a8; font-size:8pt'>Planning interne — non transmis au groupe « disponibilités ».</p>")


class ExportDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Aperçu avant impression")
        self.resize(980, 680)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 18)
        lay.setSpacing(12)
        top = QHBoxLayout()
        top.addWidget(label("Aperçu avant impression", size=17, bold=True))
        top.addSpacing(12)
        self.week = QComboBox()
        for w in range(store.grid.weeks):
            self.week.addItem(f"Semaine {w + 1} ({store.date_of(w, 0):%d/%m} – "
                              f"{store.date_of(w, store.grid.days - 1):%d/%m})", w)
        self.week.addItem("Toutes les semaines (une page par semaine)", -1)
        self.week.setCurrentIndex(min(store.offset, store.grid.weeks - 1))
        self.week.currentIndexChanged.connect(self._preview)
        top.addWidget(self.week)
        top.addStretch(1)
        close = button("Fermer")
        close.clicked.connect(self.reject)
        printer = button("Imprimer…")
        printer.clicked.connect(self._print)
        pdf = button("Enregistrer en PDF", "primary")
        pdf.clicked.connect(self._save_pdf)
        for b in (close, printer, pdf):
            top.addWidget(b)
        lay.addLayout(top)
        self.view = QTextBrowser()
        self.view.setStyleSheet("QTextBrowser { background: #ffffff; border: 1px solid #dfe5ec; border-radius: 8px; padding: 18px; }")
        lay.addWidget(self.view, 1)
        self._preview()

    def _html(self) -> str:
        w = self.week.currentData()
        if w == -1:
            pages = [week_html(self.store, i) for i in range(self.store.grid.weeks)]
            return "".join(f"<div style='page-break-after:always'>{p}</div>" for p in pages[:-1]) + pages[-1]
        return week_html(self.store, w)

    def _document(self) -> QTextDocument:
        doc = QTextDocument()
        doc.setDefaultFont(QFont("Segoe UI", 9))
        doc.setHtml(self._html())
        return doc

    def _preview(self) -> None:
        self.view.setHtml(self._html())

    @staticmethod
    def _printer() -> QPrinter:
        p = QPrinter(QPrinter.PrinterMode.HighResolution)
        p.setPageOrientation(QPageLayout.Orientation.Landscape)
        return p

    def _save_pdf(self) -> None:
        w = self.week.currentData()
        name = "horaire_toutes_semaines.pdf" if w == -1 else f"horaire_semaine{w + 1}.pdf"
        folder = self.store.data_dir or Path.home()
        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer en PDF", str(Path(folder) / name), "PDF (*.pdf)")
        if not path:
            return
        printer = self._printer()
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        self._document().print_(printer)
        self.store.message.emit("ok", f"{Path(path).name} enregistré.")
        QMessageBox.information(self, "Export PDF", f"Le planning a été enregistré :\n{path}")

    def _print(self) -> None:
        printer = self._printer()
        dlg = QPrintDialog(printer, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._document().print_(printer)
