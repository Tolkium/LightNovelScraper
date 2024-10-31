@echo off
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller
pyinstaller LightNovelScraper.spec

