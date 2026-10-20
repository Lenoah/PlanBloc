"""État de l'application : fichiers importés, séances placées et vérification des ressources."""
from __future__ import annotations

import math
import shutil
from dataclasses import dataclass
from datetime import date as Date
from datetime import time as Time
from datetime import timedelta
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal
from pydantic import ValidationError

from . import theme
from .models import (WEEK_DAYS, Activity, ActivitiesFile, Block, Calendar, DispoExport, PlanningFile,
                     Resource, Slot)

KINDS = ("personne", "local", "materiel")
KIND_OF_TYPE = {"person": "personne", "local": "local", "equipment": "materiel"}
KIND_LABEL = {"personne": "Personnes", "local": "Locaux", "materiel": "Matériels"}
FIELD_OF_KIND = {"personne": "person_id", "local": "room_id", "materiel": "material_id"}
DISPO_PATTERN = "dispo-export*.json"
ACT_FILE = "activites.json"
PLANNING_FILE = "planning.json"
DAY_NAMES = ("Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche")
VISIBLE_WEEKS = 12
OUR_GROUP = "Notre groupe"
OTHER_GROUP = "Groupe « disponibilités » · lecture seule"
PREVIEW_ID = "__apercu__"


def fmt_hours(h: float) -> str:
    h = float(h)
    return f"{int(h)} h" if h.is_integer() else f"{h:.1f} h".replace(".", ",")


class DataError(Exception):
    """Fichier absent ou invalide."""


@dataclass
class Check:
    status: str          # ok | orange | rouge | incomplet
    lines: list[str]

    @property
    def is_conflict(self) -> bool:
        return self.status in ("orange", "rouge")


@dataclass
class FileReport:
    name: str
    origin: str
    ok: bool
    detail: str


def read_model(path: Path, model):
    if not path.exists():
        raise DataError(f"{path.name} : fichier introuvable.")
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        err = exc.errors()[0]
        where = ".".join(str(p) for p in err.get("loc", ())) or "contenu"
        raise DataError(f"{path.name} : {where} — {err.get('msg', 'valeur invalide')}") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise DataError(f"{path.name} : lecture impossible ({exc}).") from None


def find_dispo(folder: Path) -> Optional[Path]:
    """Le plus récent des exports du groupe « disponibilités » (la date est dans le nom)."""
    found = sorted(Path(folder).glob(DISPO_PATTERN))
    return found[-1] if found else None


def default_export() -> DispoExport:
    """Calendrier provisoire, utilisé tant qu'aucun export n'est chargé."""
    today = Date.today()
    start = today - timedelta(days=today.weekday())
    return DispoExport(
        calendar=Calendar(start_date=start, end_date=start + timedelta(weeks=12, days=-3),
                          week_days=list(WEEK_DAYS[:5])),
        slots=[Slot(id="s1", start=Time(8), end=Time(10)), Slot(id="s2", start=Time(10, 30), end=Time(12, 30)),
               Slot(id="s3", start=Time(13, 30), end=Time(15, 30)), Slot(id="s4", start=Time(16), end=Time(18))])


class Store(QObject):
    changed = Signal()
    message = Signal(str, str)      # (statut, texte)
    offset_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.export: DispoExport = default_export()
        self.dispo_path: Optional[Path] = None
        self.filieres: dict[str, str] = {}          # id -> nom
        self.filiere_id = ""
        self.activities: list[Activity] = []
        self._base_activities: list[Activity] = []
        self._added: set[str] = set()
        self.resources: dict[str, list[Resource]] = {k: [] for k in KINDS}
        self.blocks: list[Block] = []
        self.reports: list[FileReport] = []
        self.offset = 0
        self.dirty = False
        self.data_dir: Optional[Path] = None
        self.planning_path: Optional[Path] = None
        self._res: dict[str, Resource] = {}
        self._kind: dict[str, str] = {}
        self._status: dict[str, dict[tuple[Date, str], str]] = {}
        self._acts: dict[str, Activity] = {}
        self._pos: dict[str, tuple[int, int, int]] = {}
        self._at: dict[tuple[int, int, int], list[Block]] = {}
        self._count: dict[str, int] = {}
        self._checks: dict[str, Check] = {}
        self._set_calendar(self.export)

    # ------------------------------------------------------------------ calendrier
    def _set_calendar(self, export: DispoExport) -> None:
        cal = export.calendar
        self.cal: Calendar = cal
        self.slots: list[Slot] = list(export.slots)
        self.days: list[int] = sorted({WEEK_DAYS.index(d) for d in cal.week_days})
        self.monday0 = cal.start_date - timedelta(days=cal.start_date.weekday())
        self.weeks = (cal.end_date - self.monday0).days // 7 + 1
        self.holidays = {h.on: (h.label or "Congé") for h in cal.holidays}
        self._slot_index = {s.id: i for i, s in enumerate(self.slots)}

    @property
    def slot_minutes(self) -> int:
        return self.cal.slot_duration

    @property
    def block_hours(self) -> float:
        return self.slot_minutes / 60

    def date_of(self, week: int, day: int) -> Date:
        return self.monday0 + timedelta(days=7 * week + self.days[day])

    def day_name(self, day: int) -> str:
        return DAY_NAMES[self.days[day]]

    def day_state(self, week: int, day: int) -> str:
        """« ouvert », « hors » (avant le début / après la fin du calendrier) ou « conge »."""
        on = self.date_of(week, day)
        if on < self.cal.start_date or on > self.cal.end_date:
            return "hors"
        if on in self.holidays:
            return "conge"
        return "ouvert"

    def position(self, on: Date, slot_id: str) -> Optional[tuple[int, int, int]]:
        if on.weekday() not in self.days or slot_id not in self._slot_index:
            return None
        w = (on - self.monday0).days // 7
        if not 0 <= w < self.weeks:
            return None
        return w, self.days.index(on.weekday()), self._slot_index[slot_id]

    def pos(self, b: Block) -> tuple[int, int, int]:
        return self._pos.get(b.id) or self.position(b.on, b.slot_id) or (0, 0, 0)

    def time_label(self, s: int, span: int = 1) -> str:
        last = self.slots[min(s + span, len(self.slots)) - 1]
        return f"{self.slots[s].start:%H:%M}–{last.end:%H:%M}"

    def describe(self, b: Block) -> str:
        w, d, s = self.pos(b)
        return f"Semaine {w + 1} · {self.day_name(d)} {self.date_of(w, d):%d/%m} · {self.time_label(s, b.span)}"

    # ------------------------------------------------------------------ chargement
    def load_folder(self, folder: Path, dispo_path: Optional[Path] = None) -> list[FileReport]:
        folder = Path(folder)
        reports: list[FileReport] = []
        export = acts = None
        path = Path(dispo_path) if dispo_path else find_dispo(folder)
        if path is None:
            reports.append(FileReport("dispo-export-….json", OTHER_GROUP, False,
                                      f"Aucun fichier « {DISPO_PATTERN} » dans {folder}."))
        else:
            try:
                export = read_model(path, DispoExport)
                n = {k: 0 for k in KINDS}
                for r in export.resources:
                    n[KIND_OF_TYPE[r.type]] += 1
                unav = sum(1 for r in export.resources for e in r.exceptions if e.status == "unavailable")
                cal = export.calendar
                reports.append(FileReport(path.name, OTHER_GROUP, True,
                                          f"{cal.start_date:%d/%m/%Y} → {cal.end_date:%d/%m/%Y} · "
                                          f"{n['personne']} personnes, {n['local']} locaux, {n['materiel']} matériels · "
                                          f"{unav} indisponibilités"))
            except DataError as e:
                reports.append(FileReport(path.name, OTHER_GROUP, False, str(e)))
        try:
            acts = read_model(folder / ACT_FILE, ActivitiesFile)
            n_act = sum(len(f.activities) for f in acts.filieres)
            detail = f"{len(acts.filieres)} filières · {n_act} activités"
            if export:
                known = {r.id for r in export.resources}
                unknown = {rid for f in acts.filieres for a in f.activities
                           for rid in (a.person_id, a.room_id, a.material_id) if rid and rid not in known}
                if unknown:
                    detail += f" · {len(unknown)} ressources inconnues dans l'export (à choisir dans les pop-ups)"
            reports.append(FileReport(ACT_FILE, f"{OUR_GROUP} · provisoire", True, detail))
        except DataError as e:
            reports.append(FileReport(ACT_FILE, OUR_GROUP, False, str(e)))

        if not all(r.ok for r in reports):
            self.reports = reports
            self.changed.emit()
            return reports

        self.export = export
        self.dispo_path = path
        self._set_calendar(export)
        self.resources = {k: [] for k in KINDS}
        for r in sorted(export.resources, key=lambda r: r.name.lower()):
            self.resources[KIND_OF_TYPE[r.type]].append(r)
        self._reindex()
        self.filieres = {f.id: f.name for f in acts.filieres}
        if self.filiere_id not in self.filieres:
            self.filiere_id = acts.filieres[0].id
        self._base_activities = [a for f in acts.filieres for a in f.activities]
        self.activities = list(self._base_activities)
        self._added = set()
        self.data_dir = folder
        self.planning_path = folder / PLANNING_FILE
        self.blocks = []
        self.offset = 0
        self._recompute()
        if self.planning_path.exists():
            try:
                skipped = self._apply_planning(read_model(self.planning_path, PlanningFile))
                detail = f"{len(self.blocks)} séances placées"
                if skipped:
                    detail += f" · {skipped} ignorées (hors calendrier ou activité inconnue)"
                reports.append(FileReport(PLANNING_FILE, f"{OUR_GROUP} · sauvegarde", True, detail))
            except DataError as e:
                reports.append(FileReport(PLANNING_FILE, f"{OUR_GROUP} · sauvegarde", False, str(e)))
        self.reports = reports
        self.dirty = False
        self._recompute()
        self.changed.emit()
        self.offset_changed.emit()
        n = len(self.conflicts())
        self.message.emit("ok" if n == 0 else "orange",
                          f"Planning chargé — {len(self.blocks)} séances placées"
                          + (f", {n} conflits à vérifier." if n else ", aucun conflit."))
        return reports

    def import_dispo(self, path: Path) -> list[FileReport]:
        """Copie un export de disponibilités dans le dossier de données puis recharge tout."""
        path = Path(path)
        folder = self.data_dir or path.parent
        target = folder / path.name
        if path.resolve() != target.resolve():
            shutil.copy2(path, target)
        return self.load_folder(folder, target)

    def open_planning(self, path: Path) -> None:
        pf = read_model(Path(path), PlanningFile)
        self.activities = list(self._base_activities)
        self._added = set()
        skipped = self._apply_planning(pf)
        self.planning_path = Path(path)
        self.dirty = False
        self._recompute()
        self.changed.emit()
        text = f"{Path(path).name} ouvert — {len(self.blocks)} séances."
        if skipped:
            text += f" {skipped} ignorées."
        self.message.emit("ok", text)

    def save(self, path: Optional[Path] = None) -> Path:
        path = Path(path) if path else self.planning_path
        if path is None:
            raise OSError("aucun fichier de planning défini")
        data = PlanningFile(blocks=self.blocks, extra_activities=[a for a in self.activities if a.id in self._added])
        path.write_text(data.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
        self.planning_path = path
        self.dirty = False
        self.changed.emit()
        self.message.emit("ok", f"Planning enregistré dans {path.name}.")
        return path

    def _apply_planning(self, pf: PlanningFile) -> int:
        known = {a.id for a in self.activities}
        first = next(iter(self.filieres), "")
        for a in pf.extra_activities:
            if a.id not in known:
                if a.filiere_id not in self.filieres:
                    a.filiere_id = first
                self.activities.append(a)
                self._added.add(a.id)
                known.add(a.id)
        kept, skipped = [], 0
        for b in pf.blocks:
            p = self.position(b.on, b.slot_id)
            if b.activity_id in known and p and p[2] + b.span <= len(self.slots):
                kept.append(b)
            else:
                skipped += 1
        self.blocks = kept
        return skipped

    def _reindex(self) -> None:
        self._res, self._kind, self._status = {}, {}, {}
        for kind, lst in self.resources.items():
            for r in lst:
                self._res[r.id] = r
                self._kind[r.id] = kind
                self._status[r.id] = {(e.on, e.slot_id): e.status for e in r.exceptions}

    def _recompute(self) -> None:
        self._acts = {a.id: a for a in self.activities}
        self._pos, self._at, self._count = {}, {}, {}
        for b in self.blocks:
            w, d, s = self.position(b.on, b.slot_id) or (0, 0, 0)
            self._pos[b.id] = (w, d, s)
            for i in range(b.span):
                self._at.setdefault((w, d, s + i), []).append(b)
            self._count[b.activity_id] = self._count.get(b.activity_id, 0) + b.span
        self._checks = {b.id: self.evaluate(b, *self._pos[b.id]) for b in self.blocks}

    # ------------------------------------------------------------------ filières
    @property
    def filiere(self) -> str:
        return self.filieres.get(self.filiere_id, "")

    def set_filiere(self, fid: str) -> None:
        if fid in self.filieres and fid != self.filiere_id:
            self.filiere_id = fid
            self.changed.emit()
            left = sum(self.remaining_hours(a) for a in self.filiere_activities())
            self.message.emit("ok", f"Filière « {self.filiere} » — {fmt_hours(left)} à placer.")

    def filiere_activities(self, fid: Optional[str] = None) -> list[Activity]:
        fid = fid or self.filiere_id
        return [a for a in self.activities if a.filiere_id == fid]

    def filiere_of(self, b: Block) -> str:
        a = self._acts.get(b.activity_id)
        return a.filiere_id if a else ""

    # ------------------------------------------------------------------ lecture
    def activity(self, act_id: str) -> Optional[Activity]:
        return self._acts.get(act_id)

    def activity_name(self, act_id: str) -> str:
        a = self._acts.get(act_id)
        return a.name if a else "?"

    def block(self, bid: str) -> Optional[Block]:
        return next((b for b in self.blocks if b.id == bid), None)

    def name(self, rid: str) -> str:
        r = self._res.get(rid)
        return r.name if r else ""

    def kind_of(self, rid: str) -> str:
        return self._kind.get(rid, "")

    def colors(self, act: Optional[Activity]) -> tuple[str, str]:
        if act is None:
            return theme.PALETTE[-1]
        if act.color:
            return theme.tint(act.color), act.color
        same = [a.id for a in self.activities if a.filiere_id == act.filiere_id]
        idx = same.index(act.id) if act.id in same else 0
        return theme.PALETTE[idx % len(theme.PALETTE)]

    def blocks_at(self, w: int, d: int, s: int) -> list[Block]:
        return list(self._at.get((w, d, s), []))

    def placed_count(self, act_id: str) -> int:
        return self._count.get(act_id, 0)

    def total_blocks(self, act: Activity) -> int:
        return max(1, math.ceil(act.hours / self.block_hours - 1e-9))

    def remaining_blocks(self, act: Activity) -> int:
        return max(0, self.total_blocks(act) - self.placed_count(act.id))

    def remaining_hours(self, act: Activity) -> float:
        return max(0.0, act.hours - self.placed_count(act.id) * self.block_hours)

    def session_span(self, act: Activity) -> int:
        """Nombre de créneaux de la prochaine séance (4 h avec des créneaux de 2 h = 2), limité au reste."""
        want = max(1, math.ceil(act.session_hours * 60 / self.slot_minutes - 1e-9))
        return min(want, self.remaining_blocks(act))

    def count_for_resource(self, rid: str) -> int:
        return sum(1 for b in self.blocks if rid in (b.person_id, b.room_id, b.material_id))

    def is_unavailable(self, rid: str, w: int, d: int, s: int) -> bool:
        st = self._status.get(rid)
        if st is None or not 0 <= s < len(self.slots):
            return False
        return st.get((self.date_of(w, d), self.slots[s].id), self.cal.default_status) == "unavailable"

    def used_by(self, rid: str, w: int, d: int, s: int, except_id: str = "") -> Optional[Block]:
        for o in self._at.get((w, d, s), []):
            if o.id != except_id and rid in (o.person_id, o.room_id, o.material_id):
                return o
        return None

    def availability(self, rid: str, b: Block) -> tuple[str, Optional[Block]]:
        """État d'une ressource sur tous les créneaux de la séance : libre, indisponible ou pris."""
        w, d, s = self.pos(b)
        cells = [(w, d, s + i) for i in range(b.span)]
        if any(self.is_unavailable(rid, *c) for c in cells):
            return "indisponible", None
        for c in cells:
            other = self.used_by(rid, *c, except_id=b.id)
            if other:
                return "pris", other
        return "libre", None

    def availability_label(self, rid: str, b: Block) -> str:
        state, other = self.availability(rid, b)
        if state == "pris":
            return f"{self.name(rid)} — pris par {self.activity_name(other.activity_id)}"
        return f"{self.name(rid)} — {state}"

    def check(self, b: Block) -> Check:
        return self._checks.get(b.id) or self.evaluate(b, *self.pos(b))

    def conflicts(self) -> list[Block]:
        out = [b for b in self.blocks if self.check(b).is_conflict]
        return sorted(out, key=lambda b: (b.on, self._slot_index.get(b.slot_id, 0)))

    def fits(self, w: int, d: int, s: int, span: int) -> Optional[str]:
        """None si la séance peut être posée à cet endroit, sinon la raison."""
        if not (0 <= w < self.weeks and 0 <= d < len(self.days)):
            return "En dehors du calendrier."
        state = self.day_state(w, d)
        if state == "conge":
            return f"{self.date_of(w, d):%d/%m} est un jour de congé."
        if state == "hors":
            return "Ce jour est en dehors de la période du calendrier."
        if s < 0 or s + span > len(self.slots):
            return (f"Une séance de {fmt_hours(span * self.block_hours)} doit tenir dans la journée : "
                    "choisissez un créneau plus tôt.")
        begin, end = self.slots[s].start, self.slots[s + span - 1].end
        for p in self.cal.breaks:
            if p.start < end and p.end > begin:
                return (f"La séance ne peut pas occuper « {p.name or 'la pause'} » "
                        f"({p.start:%H:%M}–{p.end:%H:%M}).")
        return None

    def evaluate(self, b: Block, w: int, d: int, s: int) -> Check:
        """Statut de la séance `b` si elle commençait en (w, d, s). Ne modifie rien."""
        reason = self.fits(w, d, s, b.span)
        if reason:
            return Check("rouge", [reason])
        cells = [(w, d, s + i) for i in range(b.span)]
        fil = self.filiere_of(b)
        lines: list[str] = []
        used = bad = 0
        for rid in (b.person_id, b.room_id, b.material_id):
            if not rid:
                continue
            used += 1
            if any(self.is_unavailable(rid, *c) for c in cells):
                bad += 1
                lines.append(f"{self.name(rid) or rid} n'est pas disponible.")
                continue
            other = next((o for c in cells if (o := self.used_by(rid, *c, except_id=b.id))), None)
            if other:
                bad += 1
                where = "" if self.filiere_of(other) == fil else f" ({self.filieres.get(self.filiere_of(other), '?')})"
                lines.append(f"{self.name(rid) or rid} est déjà pris par « {self.activity_name(other.activity_id)} »{where}.")
        clash = next((o for c in cells for o in self._at.get(c, [])
                      if o.id != b.id and self.filiere_of(o) == fil), None)
        if clash:
            lines.append(f"La filière a déjà « {self.activity_name(clash.activity_id)} » à ce moment.")
        status = "ok"
        if used and bad == used:
            status = "rouge"
        elif bad or clash:
            status = "orange"
        if not b.person_id or not b.room_id:
            if status == "ok":
                status = "incomplet"
            lines.append("Aucun local choisi." if not b.room_id else "Aucun intervenant choisi.")
        if status == "ok":
            lines.append("Tout est disponible, aucun conflit.")
        return Check(status, lines)

    def preview(self, kind: str, ident: str, offset: int, w: int, d: int, s: int) -> str:
        """Couleur à afficher sur la cellule (w, d, s) pendant un glisser : ok, orange ou rouge."""
        if kind == "new":
            act = self.activity(ident)
            if act is None or self.remaining_blocks(act) == 0:
                return "rouge"
            b = Block(id=PREVIEW_ID, activity_id=act.id, on=self.cal.start_date, slot_id=self.slots[0].id,
                      span=self.session_span(act), person_id=act.person_id, room_id=act.room_id,
                      material_id=act.material_id)
        else:
            b = self.block(ident)
            if b is None:
                return "rouge"
        status = self.evaluate(b, w, d, s - offset).status
        return "ok" if status == "incomplet" else status

    # ------------------------------------------------------------------ modifications
    def _commit(self, kind: str, text: str) -> None:
        self.dirty = True
        self._recompute()
        self.changed.emit()
        self.message.emit(kind, text)

    def _issues(self, b: Block) -> str:
        chk = self.check(b)
        return "" if chk.status == "ok" else " — " + " ".join(chk.lines)

    @staticmethod
    def _new_id(prefix: str, existing: set[str]) -> str:
        n = len(existing) + 1
        while f"{prefix}{n}" in existing:
            n += 1
        return f"{prefix}{n}"

    def _move_to(self, b: Block, w: int, d: int, s: int) -> None:
        b.on = self.date_of(w, d)
        b.slot_id = self.slots[s].id

    def place_new(self, act_id: str, w: int, d: int, s: int) -> Optional[Block]:
        act = self.activity(act_id)
        if act is None:
            return None
        if self.remaining_blocks(act) <= 0:
            self.message.emit("incomplet", f"« {act.name} » est déjà entièrement placée.")
            return None
        span = self.session_span(act)
        reason = self.fits(w, d, s, span)
        if reason:
            self.message.emit("rouge", f"« {act.name} » non placée : {reason}")
            return None
        b = Block(id=self._new_id("b", {x.id for x in self.blocks}), activity_id=act.id,
                  on=self.date_of(w, d), slot_id=self.slots[s].id, span=span,
                  person_id=act.person_id, room_id=act.room_id, material_id=act.material_id)
        self.blocks.append(b)
        self._recompute()
        text = (f"Séance de {fmt_hours(span * self.block_hours)} de « {act.name} » placée — "
                f"{self.day_name(d).lower()} {self.date_of(w, d):%d/%m}, {self.time_label(s, span)}. "
                f"Reste {fmt_hours(self.remaining_hours(act))}.")
        self._commit(self.check(b).status, text + self._issues(b))
        return b
    
    def place_repeated(self, act_id: str, w: int, d: int, s: int) -> int:
        # Je place le même cours chaque semaine.
        act = self.activity(act_id)
        if act is None:
            return 0

        nombre = 0

        for semaine in range(w, self.weeks):
            # Je vérifie s'il reste des heures à placer.
            if self.remaining_blocks(act) <= 0:
                break

            span = self.session_span(act)

            # Je vérifie si le jour et le créneau sont autorisés.
            if self.fits(semaine, d, s, span) is not None:
                continue

            # Je place le cours à la même heure.
            if self.place_new(act_id, semaine, d, s) is not None:
                nombre += 1

        return nombre

    def move_block(self, bid: str, w: int, d: int, s: int) -> None:
        b = self.block(bid)
        if b is None or self.pos(b) == (w, d, s):
            return
        reason = self.fits(w, d, s, b.span)
        if reason:
            self.message.emit("rouge", f"Séance non déplacée : {reason}")
            return
        self._move_to(b, w, d, s)
        self._recompute()
        self._commit(self.check(b).status,
                     f"« {self.activity_name(b.activity_id)} » déplacée : {self.describe(b)}." + self._issues(b))

    def remove_block(self, bid: str) -> None:
        b = self.block(bid)
        if b is None:
            return
        self.blocks.remove(b)
        self._recompute()
        act = self.activity(b.activity_id)
        left = fmt_hours(self.remaining_hours(act)) if act else "?"
        self._commit("incomplet", f"Séance retirée — « {self.activity_name(b.activity_id)} » : reste {left} à placer.")

    def set_block_resource(self, bid: str, field: str, value: str) -> None:
        b = self.block(bid)
        if b is None or field not in FIELD_OF_KIND.values() or getattr(b, field) == value:
            return
        setattr(b, field, value or "")
        self._recompute()
        chk = self.check(b)
        self._commit(chk.status, "Ressource modifiée — " + " ".join(chk.lines))

    def add_activity(self, name: str, person_id: str, room_id: str, hours: int,
                     session_hours: int = 2, filiere_id: str = "", material_id: str = "") -> Activity:
        act = Activity(id=self._new_id("a", {a.id for a in self.activities}), name=name,
                       person_id=person_id, room_id=room_id, material_id=material_id, hours=hours,
                       session_hours=session_hours, filiere_id=filiere_id or self.filiere_id)
        self.activities.append(act)
        self._added.add(act.id)
        self._commit("ok", f"« {name} » ajoutée ({fmt_hours(hours)}, séances de {fmt_hours(session_hours)}) — "
                           f"glissez-la dans le planning.")
        return act

    def shift_weeks(self, direction: int) -> None:
        new = self.offset + direction * VISIBLE_WEEKS
        if 0 <= new < self.weeks and new != self.offset:
            self.offset = new
            self.offset_changed.emit()
