# Planificateur d'activités

Application desktop (Python 3.12 + PySide6) pour construire le planning prévisionnel d'une filière à partir des
fichiers de disponibilité fournis par le groupe « disponibilités ». Pas de base de données : uniquement des fichiers JSON.

## Installation et lancement

```bash
python -m venv .venv
# Windows : .venv\Scripts\activate    —    macOS/Linux : source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Tests de la logique : `python -m pytest`

## Utilisation

- **Planning** : glissez une activité de la colonne de gauche sur un créneau → un bloc de 2 h est posé, la jauge
  grise un segment. Glissez un bloc ailleurs pour le déplacer, sur la colonne de gauche (ou bouton ✕ au survol)
  pour le retirer. Cliquez un bloc → pop-up pour changer intervenant, local et matériel.
- Un bloc en conflit est orange (une ressource pose problème) ou rouge (aucune n'est disponible), avec ⚠.
  Le placement n'est jamais bloqué.
- **Personnes / Locaux / Matériels** : un sous-onglet par ressource, tous ses cours dans la grille, créneaux
  indisponibles hachurés. Consultation seule.
- **Conflits** : liste des blocs à problème, bouton « Corriger » → même pop-up.
- **Paramètres** : date de début, nombre de semaines, import d'un autre dossier, ouvrir / enregistrer un planning.
- **Exporter PDF** : aperçu d'une semaine ou de toutes, enregistrement PDF ou impression.
- `Ctrl+S` enregistre `data/planning.json`.

## Structure

```
main.py                  point d'entrée
app/models.py            formats JSON (Pydantic)
app/store.py             état, règles de vérification, opérations (sans interface)
app/theme.py             couleurs + feuille de style Qt
app/ui/grid.py           grille du planning, blocs, cellules
app/ui/rail.py           colonne des activités avec jauges
app/ui/dialogs.py        pop-ups : bloc, nouvelle activité, export PDF
app/ui/pages.py          onglets
app/ui/dnd.py            glisser-déposer
app/main_window.py       fenêtre, barre d'onglets
data/                    fichiers d'exemple
tests/                   tests pytest
```

## Fichiers (dossier `data/`)

| Fichier | Origine | Contenu |
|---|---|---|
| `grille.json` | notre groupe | `startDate`, `weeks`, `days`, `slots[{start,end}]` |
| `activites.json` | notre groupe | `filiere`, `activities[{id,name,personId,roomId,hours}]` |
| `disponibilites_personnes.json` | groupe disponibilités | `kind: "personne"`, `slotMinutes`, `resources[{id,name,info,unavailable[{date,start,end}]}]` |
| `disponibilites_locaux.json` | groupe disponibilités | idem, `kind: "local"` |
| `disponibilites_materiel.json` | groupe disponibilités | idem, `kind: "materiel"` |
| `planning.json` | sauvegarde | `blocks[{id,activityId,week,day,slot,personId,roomId,materialId}]`, `extraActivities` |

La durée des créneaux de `grille.json` doit être égale à `slotMinutes` des fichiers de disponibilité
(granularité imposée par l'autre groupe). Une activité de 48 h avec des créneaux de 2 h = 24 blocs.

Quand le format réel de l'autre groupe sera connu, seule la lecture dans `app/models.py` / `Store.load_folder`
est à adapter.

## Règles de vérification (par bloc)

Une ressource pose problème si elle est déclarée indisponible sur ce créneau, ou si un autre bloc l'utilise déjà.
Deux blocs de la même filière au même créneau sont aussi signalés.

- OK : tout est libre · Orange : au moins un problème · Rouge : aucune ressource associée n'est disponible
- Incomplet (pointillés) : pas de local ou pas d'intervenant

## Exécutable standalone

```bash
pyinstaller --noconfirm --windowed --name Planificateur main.py
```

Copiez ensuite le dossier `data/` à côté de `dist/Planificateur/Planificateur.exe`.

## Prévu plus tard

Vue par niveau / classe (sélecteur de filière déjà présent, autres choix désactivés).
