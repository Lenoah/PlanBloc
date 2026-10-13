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

- **Planning** : choisissez la filière en haut à gauche. Glissez une activité de la colonne de gauche sur un
  créneau : pendant le glisser, chaque case se colore en **vert** (tout est libre), **orange** (une ressource
  pose problème) ou **rouge** (impossible : congé, séance qui ne tient pas dans la journée, aucune ressource
  libre). Les cases que la séance occupera sont encadrées en bleu.
- Une séance dure 2 h ou 4 h (`sessionHours`). Avec des créneaux de 2 h, une séance de 4 h occupe deux
  créneaux consécutifs du même jour (repères « 1/2 », « 2/2 ») et grise deux segments de la jauge.
- Une séance garde toujours la couleur de sa matière ; un problème ajoute un cadre orange ou rouge et ⚠.
- **Calque des disponibilités** : survolez le nom d'un intervenant ou d'un local dans une séance et appuyez
  sur **D**. La grille montre ses créneaux libres (vert), pris (orange) et indisponibles (rouge hachuré).
  **Échap** ou ✕ pour fermer.
- Glissez une séance ailleurs pour la déplacer, sur la colonne de gauche (ou ✕ au survol) pour la retirer.
  Cliquez une séance → pop-up pour changer intervenant, local et matériel.
- **Personnes / Locaux / Matériels** : un sous-onglet par ressource, ses séances de toutes les filières,
  créneaux indisponibles hachurés. Consultation seule.
- **Conflits** : séances à problème de toutes les filières, bouton « Corriger » → même pop-up.
- **Paramètres** : calendrier (lecture seule, vient de l'export), import d'un nouvel export ou d'un dossier,
  ouvrir / enregistrer un planning.
- **Exporter PDF** : horaire de la filière choisie, une semaine ou toutes.
- `Ctrl+S` enregistre `data/planning.json` (pas de sauvegarde automatique).

## Structure

```
main.py                  point d'entrée
app/models.py            formats JSON (Pydantic)
app/store.py             calendrier, état, règles de vérification, aperçu, opérations
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
| `dispo-export-AAAA-MM-JJ.json` | groupe disponibilités (lecture seule) | `calendar` (période, jours, `slotDuration`, pauses, congés, `defaultStatus`), `slots[{id,start,end}]`, `resources[{id,type,name,owner,exceptions[{date,slotId,status}]}]` |
| `activites.json` | notre groupe (provisoire) | `filieres[{id,name,activities[{id,name,personId,roomId,materialId,hours,sessionHours}]}]` |
| `planning.json` | sauvegarde | `blocks[{id,activityId,date,slotId,span,personId,roomId,materialId}]`, `extraActivities` |

- S'il y a plusieurs exports dans `data/`, le plus récent (d'après la date du nom) est utilisé.
- La grille est construite à partir de l'export : du lundi de la semaine de `startDate` jusqu'à `endDate`,
  jours `weekDays`, créneaux `slots`. Les jours avant le début ou après la fin sont grisés, les congés hachurés.
- `type` : `person` → Personnes, `local` → Locaux, `equipment` → Matériels.
- Une ressource est indisponible sur un créneau si son exception (date + `slotId`) ou, à défaut,
  `defaultStatus` vaut `unavailable`.
- Les séances sont enregistrées par date et `slotId` : un nouvel export ne les décale pas.
- Les activités viendront plus tard d'ailleurs ; seule la lecture d'`activites.json` sera à adapter.

## Règles de vérification (par séance, sur tous ses créneaux)

- Une ressource pose problème si elle est indisponible, ou déjà prise par une autre séance
  (de n'importe quelle filière). Deux séances de la même filière au même moment sont aussi signalées.
- OK : tout est libre · Orange : au moins un problème · Rouge : aucune ressource associée n'est disponible.
  Le message cite uniquement les ressources en cause.
- Incomplet (pointillés) : pas de local ou pas d'intervenant.
- Refusé (rien n'est posé) : jour de congé, hors calendrier, séance qui dépasse la fin de journée
  ou qui occupe une pause (ex. pause de midi 12:30–13:30).

## Exécutable standalone

```bash
pyinstaller --noconfirm --windowed --name Planificateur main.py
```

Copiez ensuite le dossier `data/` à côté de `dist/Planificateur/Planificateur.exe`.

## Prévu plus tard

Vue par niveau / classe.
