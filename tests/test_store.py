"""Tests de la logique (sans interface) : python -m pytest

Données : l'export réel du groupe « disponibilités » (data/dispo-export-*.json) et notre
activites.json, copiés dans un dossier temporaire sans planning.json.
Semaine 0 = 12/10 → 16/10 (le calendrier commence le mercredi 14/10).
"""
import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from app.store import Store, find_dispo

DATA = Path(__file__).resolve().parent.parent / "data"
CHRISTIAN = "cmv49r1q0000106l50dbo6wab"
A201 = "cmv4bf60c000306icnb3zzxcb"


@pytest.fixture
def s(tmp_path) -> Store:
    shutil.copy(find_dispo(DATA), tmp_path)
    shutil.copy(DATA / "activites.json", tmp_path)
    st = Store()
    reports = st.load_folder(tmp_path)
    assert all(r.ok for r in reports), [r.detail for r in reports if not r.ok]
    return st


def test_calendrier_lu_depuis_l_export(s):
    assert s.block_hours == 2
    assert s.weeks == 12                         # du lundi 12/10 au jeudi 31/12
    assert len(s.days) == 5 and len(s.slots) == 4
    assert s.slots[1].label("–") == "10:30–12:30"
    assert s.day_state(0, 0) == "hors"           # lundi 12/10, avant le début
    assert s.day_state(0, 2) == "ouvert"         # mercredi 14/10
    assert s.day_state(4, 0) == "conge"          # lundi 09/11
    assert len(s.filieres) == 3
    assert len(s.resources["personne"]) == 2


def test_seance_de_4h_occupe_deux_creneaux(s):
    a = s.activity("a1")                         # 48 h, séances de 4 h
    b = s.place_new("a1", 0, 2, 0)
    assert b.span == 2
    assert s.placed_count("a1") == 2
    assert s.remaining_hours(a) == 44
    assert b in s.blocks_at(0, 2, 1)


def test_seance_qui_deborde_de_la_journee_refusee(s):
    assert s.place_new("a1", 0, 2, 3) is None    # 16:00 + 4 h : pas de créneau après
    assert s.placed_count("a1") == 0


def test_seance_qui_chevauche_la_pause_refusee(s):
    assert s.preview("new", "a1", 0, 0, 2, 1) == "rouge"    # 10:30 → 15:30 traverse 12:30–13:30
    assert s.place_new("a1", 0, 2, 1) is None
    assert s.place_new("a1", 0, 2, 2) is not None           # 13:30 → 18:00 : après la pause
    assert s.place_new("a2", 0, 3, 1) is not None           # 2 h à 10:30 : finit à 12:30, ok


def test_conge_et_hors_calendrier_refuses(s):
    assert s.place_new("a2", 4, 0, 0) is None    # 09/11 congé
    assert s.place_new("a2", 0, 0, 0) is None    # 12/10 avant le début


def test_derniere_seance_raccourcie_au_reste(s):
    a = s.activity("a6")                         # 30 h en séances de 2 h
    a.session_hours = 4
    for i in range(7):
        s.place_new("a6", 1 + i // 4, 1 + i % 4, 0)
    assert s.remaining_hours(a) == 2
    b = s.place_new("a6", 3, 1, 0)
    assert b.span == 1


def test_local_indisponible_donne_orange_et_le_nomme(s):
    b = s.place_new("a2", 1, 0, 0)               # A.201 indisponible le lundi 19/10
    chk = s.check(b)
    assert chk.status == "orange"
    assert chk.lines == ["A.201 n'est pas disponible."]


def test_rouge_cite_seulement_les_ressources(s):
    b = s.place_new("a2", 1, 0, 0)
    s.set_block_resource(b.id, "person_id", CHRISTIAN)   # indisponible le 19/10
    s.set_block_resource(b.id, "material_id", "")
    chk = s.check(b)
    assert chk.status == "rouge"
    assert chk.lines == ["Christian Loïc KOUNGOUE DIEPE n'est pas disponible.", "A.201 n'est pas disponible."]


def test_ressource_prise_par_une_autre_filiere(s):
    s.place_new("a1", 0, 2, 0)                   # Christian, mercredi 08:00
    s.set_filiere("info-b1")
    b = s.place_new("i2", 0, 2, 1)               # Christian aussi, 10:30
    chk = s.check(b)
    assert chk.status == "orange"
    assert any("Programmation Python" in l and "Informatique — Bloc 2" in l for l in chk.lines)
    assert not any("La filière a déjà" in l for l in chk.lines)


def test_apercu_avant_de_poser(s):
    assert s.preview("new", "a1", 0, 0, 2, 0) == "ok"
    assert s.preview("new", "a1", 0, 1, 0, 0) == "orange"   # Christian indisponible le 19/10
    assert s.preview("new", "a1", 0, 0, 2, 3) == "rouge"    # ne tient pas dans la journée
    assert s.preview("new", "a1", 0, 4, 0, 0) == "rouge"    # congé
    assert s.blocks == []                                   # l'aperçu ne pose rien


def test_deplacer_en_attrapant_la_deuxieme_partie(s):
    b = s.place_new("a1", 0, 2, 0)
    assert s.preview("move", b.id, 1, 0, 3, 3) == "ok"      # 2e partie lâchée à 16:00 → début 13:30
    s.move_block(b.id, 0, 3, 2)
    assert s.pos(b) == (0, 3, 2)
    assert b.on == date(2026, 10, 15) and b.slot_id == "s3"


def test_retirer_rend_les_heures(s):
    a = s.activity("a1")
    b = s.place_new("a1", 0, 2, 0)
    s.remove_block(b.id)
    assert s.remaining_hours(a) == 48


def test_sauvegarde_et_rechargement(s, tmp_path):
    s.place_new("a1", 0, 2, 0)
    s.add_activity("Atelier Git", CHRISTIAN, A201, 8, session_hours=4)
    path = s.save(tmp_path / "planning.json")
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["blocks"][0]["date"] == "2026-10-14" and saved["blocks"][0]["slotId"] == "s1"
    s2 = Store()
    s2.load_folder(tmp_path)
    assert len(s2.blocks) == 1 and s2.blocks[0].span == 2
    git = next(a for a in s2.activities if a.name == "Atelier Git")
    assert git.session_hours == 4 and git.filiere_id == "info-b2"
