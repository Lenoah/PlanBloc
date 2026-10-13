"""Formats des fichiers JSON, validés avec Pydantic."""
from __future__ import annotations

from datetime import date as Date
from datetime import time as Time
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class Model(BaseModel):
    """Base : champs Python en snake_case, JSON en camelCase."""
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)


class Slot(Model):
    start: Time
    end: Time

    @model_validator(mode="after")
    def _check_order(self):
        if self.end <= self.start:
            raise ValueError("l'heure de fin doit suivre l'heure de début")
        return self

    @property
    def minutes(self) -> int:
        return (self.end.hour * 60 + self.end.minute) - (self.start.hour * 60 + self.start.minute)

    def label(self, sep: str = " – ") -> str:
        return f"{self.start:%H:%M}{sep}{self.end:%H:%M}"


class GridConfig(Model):
    """grille.json — configuration de la grille (notre groupe)."""
    start_date: Date
    weeks: int = Field(12, ge=1, le=52)
    days: int = Field(5, ge=1, le=7)
    slots: list[Slot] = Field(min_length=1)


class Unavailability(Model):
    on: Date = Field(alias="date")
    start: Time
    end: Time

    @model_validator(mode="after")
    def _check_order(self):
        if self.end <= self.start:
            raise ValueError("l'heure de fin doit suivre l'heure de début")
        return self


class Resource(Model):
    id: str
    name: str
    info: str = ""
    unavailable: list[Unavailability] = Field(default_factory=list)


class AvailabilityFile(Model):
    """disponibilites_*.json — produits par le groupe « disponibilités » (lecture seule)."""
    kind: Literal["personne", "local", "materiel"]
    slot_minutes: int = Field(120, ge=15)
    resources: list[Resource]


class Activity(Model):
    id: str
    name: str
    person_id: str = ""
    room_id: str = ""
    hours: int = Field(ge=1)
    color: Optional[str] = None


class ActivitiesFile(Model):
    """activites.json — activités à planifier (notre groupe)."""
    filiere: str
    activities: list[Activity]


class Block(Model):
    """Un bloc = une partie d'activité de la durée d'un créneau, posée dans la grille."""
    id: str
    activity_id: str
    week: int = Field(ge=0)
    day: int = Field(ge=0)
    slot: int = Field(ge=0)
    person_id: str = ""
    room_id: str = ""
    material_id: str = ""


class PlanningFile(Model):
    """planning.json — sauvegarde du planning (usage interne uniquement)."""
    filiere: str = ""
    blocks: list[Block] = Field(default_factory=list)
    extra_activities: list[Activity] = Field(default_factory=list)
