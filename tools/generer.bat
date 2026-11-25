@echo off
rem Régénère FarmDB.lua de PoGrinder. Lancer jeu fermé de préférence (les SavedVariables sont écrits à la déconnexion).
cd /d "%~dp0"
python -I gen.py "%~dp0..\.."
pause
