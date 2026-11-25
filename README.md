# PoGrinder

Addon WoW qui liste les ressources les plus rentables à farmer, d'après les prix TSM, et propose une zone de farm.

**Cible : WoW Forever** (`_forever_\Interface\AddOns`, interface 16001). Pas Retail.

## Installation

Copier le dossier `PoGrinder/` dans `World of Warcraft\_forever_\Interface\AddOns\`. TradeSkillMaster recommandé (prix).

## Contenu

- `PoGrinder/` : l'addon (prix TSM, base objet→zone `FarmDB.lua`, log de loot, commandes).
- `tools/` : `gen.py` régénère `FarmDB.lua` depuis QuestieDB (Forever). Voir `tools/README.md`.

## État

1. Prix TSM : fait.
2. Base objet→zone : fait.
3. Score or/heure par zone : en cours.
4. Interface (+ TomTom) : à faire.
