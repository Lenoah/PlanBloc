"""État de l'application : fichiers importés, blocs placés et vérification des ressources."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date as Date
from datetime import time as Time
from datetime import timedelta
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal
from pydantic import ValidationError

from . import theme
from .models import (Activity, ActivitiesFile, AvailabilityFile, Block, GridConfig,
                     PlanningFile, Resource, Slot)

KINDS = ("personne", "local", "materiel")
KIND_LABEL = {"personne": "Personnes", "local": "Locaux", "materiel": "Matériels"}
FIELD_OF_KIND = {"personne": "person_id", "local": "room_id", "materiel": "material_id"}
GRID_FILE = "grille.json"
ACT_FILE = "activites.json"
PLANNING_FILE = "planning.json"
AVAIL_FILES = {
    "personne": "disponibilites_personnes.json",
    "local": "disponibilites_locaux.json",
    "materiel": "disponibilites_materiel.json",
}
DAY_NAMES = ("Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche")
VISIBLE_WEEKS = 6
OUR_GROUP = "Notre groupe"
OTHER_GROUP = "Groupe « disponibilités » · lecture seule"


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


class Store(QObject):
    changed = Signal()
    message = Signal(str, str)      # (statut, texte)
    offset_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.grid = GridConfig(start_date=Date(2026, 9, 14), slots=[
            Slot(start=Time(8), end=Time(10)), Slot(start=Time(10), end=Time(12)),
            Slot(start=Time(13), end=Time(15)), Slot(start=Time(15), end=Time(17))])
        self.filiere = ""
        self.activities: list[Activity] = []
        self._base_activities: list[Activity] = []
        self._added: set[str] = set()
        self.resources: dict[str, list[Resource]] = {k: [] for k in KINDS}
        self.slot_minutes = 120
        self.blocks: list[Block] = []
        self.reports: list[FileReport] = []
        self.offset = 0
        self.dirty = False
        self.data_dir: Optional[Path] = None
        self.planning_path: Optional[Path] = None
        self._res: dict[str, Resource] = {}
        self._kind: dict[str, str] = {}
        self._acts: dict[str, Activity] = {}
        self._at: dict[tuple[int, int, int], list[Block]] = {}
        self._count: dict[str, int] = {}
        self._checks: dict[str, Check] = {}

    # ------------------------------------------------------------------ chargement
    def load_folder(self, folder: Path) -> list[FileReport]:
        folder = Path(folder)
        reports: list[FileReport] = []
        grid = acts = None
        avail: dict[str, AvailabilityFile] = {}
        try:
            grid = read_model(folder / GRID_FILE, GridConfig)
            reports.append(FileReport(GRID_FILE, OUR_GROUP, True,
                                      f"Début {grid.start_date:%d/%m/%Y} · {grid.weeks} semaines · "
                                      f"{grid.days} jours · {len(grid.slots)} créneaux par jour"))
        except DataError as e:
            reports.append(FileReport(GRID_FILE, OUR_GROUP, False, str(e)))
        try:
            acts = read_model(folder / ACT_FILE, ActivitiesFile)
            reports.append(FileReport(ACT_FILE, OUR_GROUP, True,
                                      f"{acts.filiere} · {len(acts.activities)} activités"))
        except DataError as e:
            reports.append(FileReport(ACT_FILE, OUR_GROUP, False, str(e)))
        for kind, fname in AVAIL_FILES.items():
            try:
                f = read_model(folder / fname, AvailabilityFile)
                if f.kind != kind:
                    raise DataError(f"{fname} : « kind » vaut « {f.kind} », « {kind} » attendu.")
                avail[kind] = f
                n = sum(len(r.unavailable) for r in f.resources)
                reports.append(FileReport(fname, OTHER_GROUP, True,
                                          f"{len(f.resources)} {KIND_LABEL[kind].lower()} · {n} indisponibilités"))
            except DataError as e:
                reports.append(FileReport(fname, OTHER_GROUP, False, str(e)))

        if grid and len(avail) == len(KINDS):
            minutes = {f.slot_minutes for f in avail.values()}
            if len(minutes) > 1:
                reports.append(FileReport("Granularité", OTHER_GROUP, False,
                                          "Les fichiers de disponibilité n'ont pas la même durée de créneau."))
            else:
                m = next(iter(minutes))
                if any(s.minutes != m for s in grid.slots):
                    reports.append(FileReport(GRID_FILE, OUR_GROUP, False,
                                              f"Chaque créneau doit durer {m} min (granularité imposée "
                                              f"par le groupe « disponibilités »)."))

        if not all(r.ok for r in reports):
            self.reports = reports
            self.changed.emit()
            return reports

        self.grid = grid
        self.filiere = acts.filiere
        self._base_activities = list(acts.activities)
        self.activities = list(acts.activities)
        self._added = set()
        self.resources = {k: list(avail[k].resources) for k in KINDS}
        self.slot_minutes = avail["personne"].slot_minutes
        self.data_dir = folder
        self.planning_path = folder / PLANNING_FILE
        self.blocks = []
        self.offset = 0
        self._reindex()
        if self.planning_path.exists():
            try:
                skipped = self._apply_planning(read_model(self.planning_path, PlanningFile))
                detail = f"{len(self.blocks)} blocs placés"
                if skipped:
                    detail += f" · {skipped} blocs ignorés (hors grille ou activité inconnue)"
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
                          f"Planning chargé — {len(self.blocks)} blocs placés"
                          + (f", {n} conflits à vérifier." if n else ", aucun conflit."))
        return reports

    def open_planning(self, path: Path) -> None:
        pf = read_model(Path(path), PlanningFile)
        self.activities = list(self._base_activities)
        self._added = set()
        skipped = self._apply_planning(pf)
        self.planning_path = Path(path)
        self.dirty = False
        self._recompute()
        self.changed.emit()
        text = f"{Path(path).name} ouvert — {len(self.blocks)} blocs."
        if skipped:
            text += f" {skipped} blocs ignorés."
        self.message.emit("ok", text)

    def save(self, path: Optional[Path] = None) -> Path:
        path = Path(path) if path else self.planning_path
        if path is None:
            raise OSError("aucun fichier de planning défini")
        data = PlanningFile(filiere=self.filiere, blocks=self.blocks,
                            extra_activities=[a for a in self.activities if a.id in self._added])
        path.write_text(data.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
        self.planning_path = path
        self.dirty = False
        self.changed.emit()
        self.message.emit("ok", f"Planning enregistré dans {path.name}.")
        return path

    def _apply_planning(self, pf: PlanningFile) -> int:
        known = {a.id for a in self.activities}
        for a in pf.extra_activities:
            if a.id not in known:
                self.activities.append(a)
                self._added.add(a.id)
                known.add(a.id)
        g = self.grid
        kept, skipped = [], 0
        for b in pf.blocks:
            if (b.activity_id in known and b.week < g.weeks and b.day < g.days
                    and b.slot < len(g.slots)):
                kept.append(b)
            else:
                skipped += 1
        self.blocks = kept
        return skipped

    def _reindex(self) -> None:
        self._res, self._kind = {}, {}
        for kind, lst in self.resources.items():
            for r in lst:
                self._res[r.id] = r
                self._kind[r.id] = kind

    def _recompute(self) -> None:
        self._acts = {a.id: a for a in self.activities}
        self._at, self._count = {}, {}
        for b in self.blocks:
            self._at.setdefault((b.week, b.day, b.slot), []).append(b)
            self._count[b.activity_id] = self._count.get(b.activity_id, 0) + 1
        self._checks = {b.id: self._compute_check(b) for b in self.blocks}

    # ------------------------------------------------------------------ lecture
    @property
    def block_hours(self) -> float:
        return self.slot_minutes / 60

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
        idx = next((i for i, a in enumerate(self.activities) if a.id == act.id), 0)
        return theme.PALETTE[idx % len(theme.PALETTE)]

    def date_of(self, week: int, day: int) -> Date:
        return self.grid.start_date + timedelta(days=7 * week + day)

    def describe(self, b: Block) -> str:
        return (f"Semaine {b.week + 1} · {DAY_NAMES[b.day]} {self.date_of(b.week, b.day):%d/%m} · "
                f"{self.grid.slots[b.slot].label('–')}")

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

    def count_for_resource(self, rid: str) -> int:
        return sum(1 for b in self.blocks if rid in (b.person_id, b.room_id, b.material_id))

    def is_unavailable(self, rid: str, w: int, d: int, s: int) -> bool:
        r = self._res.get(rid)
        if not r or not r.unavailable or s >= len(self.grid.slots):
            return False
        day, sl = self.date_of(w, d), self.grid.slots[s]
        return any(u.on == day and u.start < sl.end and u.end > sl.start for u in r.unavailable)

    def used_by(self, rid: str, w: int, d: int, s: int, except_id: str = "") -> Optional[Block]:
        for o in self._at.get((w, d, s), []):
            if o.id != except_id and rid in (o.person_id, o.room_id, o.material_id):
                return o
        return None

    def availability(self, rid: str, b: Block) -> tuple[str, Optional[Block]]:
        if self.is_unavailable(rid, b.week, b.day, b.slot):
            return "indisponible", None
        other = self.used_by(rid, b.week, b.day, b.slot, b.id)
        return ("pris", other) if other else ("libre", None)

    def availability_label(self, rid: str, b: Block) -> str:
        state, other = self.availability(rid, b)
        if state == "pris":
            return f"{self.name(rid)} — pris par {self.activity_name(other.activity_id)}"
        return f"{self.name(rid)} — {state}"

    def check(self, b: Block) -> Check:
        return self._checks.get(b.id) or self._compute_check(b)

    def conflicts(self) -> list[Block]:
        out = [b for b in self.blocks if self.check(b).is_conflict]
        return sorted(out, key=lambda b: (b.week, b.day, b.slot))

    def _compute_check(self, b: Block) -> Check:
        lines: list[str] = []
        used = bad = 0
        for rid in (b.person_id, b.room_id, b.material_id):
            if not rid:
                continue
            used += 1
            state, other = self.availability(rid, b)
            if state == "indisponible":
                bad += 1
                lines.append(f"{self.name(rid)} n'est pas disponible à ce créneau.")
            elif state == "pris":
                bad += 1
                lines.append(f"{self.name(rid)} est déjà pris par « {self.activity_name(other.activity_id)} ».")
        clash = next((o for o in self._at.get((b.week, b.day, b.slot), []) if o.id != b.id), None)
        if clash:
            lines.append(f"La filière a déjà « {self.activity_name(clash.activity_id)} » à ce créneau.")
        status = "ok"
        if used > 1 and bad == used:
            status = "rouge"
        elif bad or clash:
            status = "orange"
        if not b.person_id or not b.room_id:
            if status == "ok":
                status = "incomplet"
            lines.append("Aucun local choisi." if not b.room_id else "Aucun intervenant choisi.")
        if status == "rouge":
            lines.insert(0, "Ce bloc ne peut pas avoir lieu : aucune ressource n'est disponible.")
        if status == "ok":
            lines.append("Tout est disponible, aucun conflit.")
        return Check(status, lines)

    # ------------------------------------------------------------------ modifications
    def _commit(self, kind: str, text: str) -> None:
        self.dirty = True
        self._recompute()
        self.changed.emit()
        self.message.emit(kind, text)

    def _issues(self, b: Block) -> str:
        chk = self.check(b)
        if chk.status == "ok":
            return ""
        return " — " + " ".join(l for l in chk.lines if not l.startswith("Ce bloc"))

    @staticmethod
    def _new_id(prefix: str, existing: set[str]) -> str:
        n = len(existing) + 1
        while f"{prefix}{n}" in existing:
            n += 1
        return f"{prefix}{n}"

    def place_new(self, act_id: str, w: int, d: int, s: int) -> Optional[Block]:
        act = self.activity(act_id)
        if act is None:
            return None
        if self.remaining_blocks(act) <= 0:
            self.message.emit("incomplet", f"« {act.name} » est déjà entièrement placée.")
            return None
        b = Block(id=self._new_id("b", {x.id for x in self.blocks}), activity_id=act.id,
                  week=w, day=d, slot=s, person_id=act.person_id, room_id=act.room_id)
        self.blocks.append(b)
        self._recompute()
        text = (f"Bloc de {fmt_hours(self.block_hours)} de « {act.name} » placé — "
                f"{DAY_NAMES[d].lower()} {self.date_of(w, d):%d/%m}, {self.grid.slots[s].label('–')}. "
                f"Reste {fmt_hours(self.remaining_hours(act))}.")
        self._commit(self.check(b).status, text + self._issues(b))
        return b

    def move_block(self, bid: str, w: int, d: int, s: int) -> None:
        b = self.block(bid)
        if b is None or (b.week, b.day, b.slot) == (w, d, s):
            return
        b.week, b.day, b.slot = w, d, s
        self._recompute()
        self._commit(self.check(b).status,
                     f"« {self.activity_name(b.activity_id)} » déplacé : {self.describe(b)}." + self._issues(b))

    def remove_block(self, bid: str) -> None:
        b = self.block(bid)
        if b is None:
            return
        self.blocks.remove(b)
        self._recompute()
        act = self.activity(b.activity_id)
        left = fmt_hours(self.remaining_hours(act)) if act else "?"
        self._commit("incomplet", f"Bloc retiré — « {self.activity_name(b.activity_id)} » : reste {left} à placer.")

    def set_block_resource(self, bid: str, field: str, value: str) -> None:
        b = self.block(bid)
        if b is None or field not in FIELD_OF_KIND.values() or getattr(b, field) == value:
            return
        setattr(b, field, value or "")
        self._recompute()
        chk = self.check(b)
        text = "Ressource modifiée — " + (" ".join(chk.lines))
        self._commit(chk.status, text)

    def add_activity(self, name: str, person_id: str, room_id: str, hours: int) -> Activity:
        act = Activity(id=self._new_id("a", {a.id for a in self.activities}), name=name,
                       person_id=person_id, room_id=room_id, hours=hours)
        self.activities.append(act)
        self._added.add(act.id)
        self._commit("ok", f"« {name} » ajoutée ({fmt_hours(hours)}, {self.total_blocks(act)} blocs) — "
                           f"glissez-la dans le planning.")
        return act

    def set_grid(self, start_date: Optional[Date] = None, weeks: Optional[int] = None) -> bool:
        update = {}
        if weeks is not None and weeks != self.grid.weeks:
            last = max((b.week for b in self.blocks), default=-1)
            if weeks <= last:
                self.message.emit("orange", f"Impossible : des blocs sont placés jusqu'à la semaine {last + 1}.")
                self.changed.emit()
                return False
            update["weeks"] = weeks
        if start_date is not None and start_date != self.grid.start_date:
            update["start_date"] = start_date
        if not update:
            return True
        self.grid = self.grid.model_copy(update=update)
        if self.offset >= self.grid.weeks:
            self.offset = 0
            self.offset_changed.emit()
        self._commit("ok", "Configuration de la grille mise à jour.")
        return True

    def shift_weeks(self, direction: int) -> None:
        new = self.offset + direction * VISIBLE_WEEKS
        if 0 <= new < self.grid.weeks and new != self.offset:
            self.offset = new
            self.offset_changed.emit()
