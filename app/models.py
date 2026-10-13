"""Formats des fichiers JSON, validés avec Pydantic."""
from __future__ import annotations

from datetime import date as Date
from datetime import datetime as DateTime
from datetime import time as Time
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

WEEK_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


class Model(BaseModel):
    """Base : champs Python en snake_case, JSON en camelCase."""
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)


def _minutes(t: Time) -> int:
    return t.hour * 60 + t.minute


# ---------------------------------------------------------------- export du groupe « disponibilités »
class Slot(Model):
    id: str
    start: Time
    end: Time

    @model_validator(mode="after")
    def _check_order(self):
        if self.end <= self.start:
            raise ValueError(f"créneau {self.id} : l'heure de fin doit suivre l'heure de début")
        return self

    @property
    def minutes(self) -> int:
        return _minutes(self.end) - _minutes(self.start)

    def label(self, sep: str = " – ") -> str:
        return f"{self.start:%H:%M}{sep}{self.end:%H:%M}"


class Break(Model):
    name: str = ""
    start: Time
    end: Time


class Holiday(Model):
    on: Date = Field(alias="date")
    label: Optional[str] = None


class Calendar(Model):
    name: str = ""
    start_date: Date
    end_date: Date
    week_days: list[Literal[WEEK_DAYS]] = Field(min_length=1)
    day_start: Optional[Time] = None
    day_end: Optional[Time] = None
    slot_duration: int = Field(120, ge=15)
    slot_gap: int = 0
    breaks: list[Break] = Field(default_factory=list)
    holidays: list[Holiday] = Field(default_factory=list)
    default_status: Literal["available", "unavailable"] = "available"

    @model_validator(mode="after")
    def _check_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("endDate doit suivre startDate")
        return self


class Exception_(Model):
    """Exception à la disponibilité par défaut, pour un créneau d'une date."""
    on: Date = Field(alias="date")
    slot_id: str
    status: Literal["available", "unavailable"]
    comment: Optional[str] = None


class Resource(Model):
    id: str
    type: Literal["person", "local", "equipment"]
    name: str
    owner: Optional[str] = None
    exceptions: list[Exception_] = Field(default_factory=list)


class Meta(Model):
    exported_at: Optional[DateTime] = None
    exported_by: Optional[str] = None


class DispoExport(Model):
    """dispo-export-AAAA-MM-JJ.json — produit par le groupe « disponibilités » (lecture seule)."""
    meta: Optional[Meta] = None
    calendar: Calendar
    slots: list[Slot] = Field(min_length=1)
    resources: list[Resource] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_slots(self):
        ids = [s.id for s in self.slots]
        if len(set(ids)) != len(ids):
            raise ValueError("deux créneaux ont le même identifiant")
        for s in self.slots:
            if s.minutes != self.calendar.slot_duration:
                raise ValueError(f"le créneau {s.id} dure {s.minutes} min au lieu de "
                                 f"{self.calendar.slot_duration} (slotDuration)")
        self.slots.sort(key=lambda s: s.start)
        return self


# ---------------------------------------------------------------- nos fichiers
class Activity(Model):
    id: str
    name: str
    person_id: str = ""
    room_id: str = ""
    material_id: str = ""
    hours: int = Field(ge=1)
    session_hours: int = Field(2, ge=1)     # durée d'une séance : 2 h, 4 h…
    color: Optional[str] = None
    filiere_id: str = ""                    # rempli au chargement


class Filiere(Model):
    id: str
    name: str
    activities: list[Activity] = Field(default_factory=list)


class ActivitiesFile(Model):
    """activites.json — filières et activités à planifier (notre groupe, provisoire)."""
    filieres: list[Filiere] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self):
        seen: set[str] = set()
        for f in self.filieres:
            for a in f.activities:
                if a.id in seen:
                    raise ValueError(f"l'identifiant d'activité « {a.id} » est utilisé deux fois")
                seen.add(a.id)
                a.filiere_id = f.id
        return self


class Block(Model):
    """Une séance posée dans la grille : `span` créneaux consécutifs à partir de `slot_id`."""
    id: str
    activity_id: str
    on: Date = Field(alias="date")
    slot_id: str
    span: int = Field(1, ge=1)
    person_id: str = ""
    room_id: str = ""
    material_id: str = ""


class PlanningFile(Model):
    """planning.json — sauvegarde du planning (usage interne uniquement)."""
    blocks: list[Block] = Field(default_factory=list)
    extra_activities: list[Activity] = Field(default_factory=list)
