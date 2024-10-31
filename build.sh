#!/bin/bash
python3 -m pip install --upgrade pip
pip3 install -r requirements.txt
pip3 install pyinstaller
pyinstaller LightNovelScraper.spec