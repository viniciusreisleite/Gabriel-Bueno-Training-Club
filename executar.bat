@echo off
cd /d "%~dp0"
echo Baixando ultimos posts do Instagram...
python baixar_mural.py

echo Enviando atualizacoes para o GitHub Pages...
git add data.json media_*.mp4
git commit -m "Atualizacao automatica mural"
git push origin main

echo Concluido! Em ~40 segundos a TV estara atualizada.
timeout /t 5