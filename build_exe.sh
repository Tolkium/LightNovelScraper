#!/bin/bash
echo "Building LightNovelScraper executable..."
echo

echo "Installing requirements..."
pip3 install -r requirements.txt

echo
echo "Creating executable..."
pyinstaller --clean \
    --onefile \
    --name LightNovelScraper \
    --console \
    --log-level INFO \
    LightNovelScraper.py

echo
echo "Build complete! Executable is in the dist folder."