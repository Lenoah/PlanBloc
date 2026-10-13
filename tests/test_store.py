"""Tests de la logique (sans interface) : python -m pytest"""
from pathlib import Path

from app.store import Store

DATA = Path(__file__).resolve().parent.parent / "data"


def make() -> Store:
    s = Store()
    reports = s.load_folder(DATA)
    assert all(r.ok for r in reports), [r.detail for r in reports if not r.ok]
    return s


def test_chargement():
    s = make()
    assert len(s.activities) == 7
    assert s.block_hours == 2
    assert len(s.blocks) == 35


def test_jauge_diminue_quand_on_place_un_bloc():
    s = make()
    a = s.activity("a7")
    avant = s.remaining_hours(a)
    s.place_new("a7", 7, 0, 0)
    assert s.remaining_hours(a) == avant - 2


def test_activite_complete_refusee():
    s = make()
    a = s.activity("a7")             # 4 h = 2 blocs, 1 déjà placé
    s.place_new("a7", 7, 0, 0)
    assert s.remaining_blocks(a) == 0
    assert s.place_new("a7", 7, 1, 0) is None
    assert s.placed_count("a7") == 2


def test_retirer_un_bloc_rend_les_heures():
    s = make()
    a = s.activity("a1")
    b = next(x for x in s.blocks if x.activity_id == "a1")
    avant = s.remaining_hours(a)
    s.remove_block(b.id)
    assert s.remaining_hours(a) == avant + 2


def test_personne_indisponible_donne_orange():
    s = make()
    b = s.place_new("a1", 0, 2, 2)    # Mme Dupont indisponible mercredi 16/09 13h-15h
    chk = s.check(b)
    assert chk.status == "orange"
    assert any("Mme Dupont" in l for l in chk.lines)


def test_aucune_ressource_disponible_donne_rouge():
    s = make()
    b = s.place_new("a7", 0, 0, 2)    # Mme Moreau indisponible + Auditoire indisponible
    assert s.check(b).status == "rouge"


def test_changer_le_local_resout_le_conflit():
    s = make()
    b = s.place_new("a7", 6, 0, 0)
    s.set_block_resource(b.id, "room_id", "r6")
    assert s.check(b).status == "ok"
    s.set_block_resource(b.id, "person_id", "")
    assert s.check(b).status == "incomplet"


def test_sauvegarde_et_rechargement(tmp_path):
    s = make()
    s.place_new("a5", 8, 3, 1)
    s.add_activity("Atelier Git", "p2", "r1", 6)
    path = s.save(tmp_path / "planning.json")
    s2 = make()
    s2.open_planning(path)
    assert len(s2.blocks) == len(s.blocks)
    assert any(a.name == "Atelier Git" for a in s2.activities)
