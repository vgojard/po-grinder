@echo off
rem Régénère FarmDB.lua de PoGrinder. Lancer de préférence jeu fermé (les SavedVariables sont écrits à la déconnexion).
cd /d "%~dp0"
python -I gen.py "C:\Program Files (x86)\World of Warcraft\_forever_\Interface\AddOns"
pause
