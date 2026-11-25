# Générer FarmDB.lua

Source : la base QuestieDB (Forever) installée dans le dossier AddOns.

    python3 -I gen.py "<...>/_forever_/Interface/AddOns" FarmDB.lua

Puis copier FarmDB.lua dans le dossier de l'addon. À relancer quand QuestieDB est mis à jour.

## Données cmangos (a priori PO, gris, taux de drop, rendement des nœuds)

`data/cmangos_*.tsv` sont extraits de la base open source cmangos classic-db :

    python3 -I cmangos_extract.py ClassicDB_1_12_1_xxx.sql.gz data/

`gen.py` produit aussi `ZoneDB.lua` (or/h par zone, utilisé par `/pogrind`).
