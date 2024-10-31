@echo off
echo Building LightNovelScraper executable...
echo.

echo Checking if executable exists and closing it...
taskkill /F /IM LightNovelScraper.exe 2>NUL

echo Checking if PyInstaller is installed...
python -c "import PyInstaller" 2>NUL
if %errorlevel% neq 0 (
    echo PyInstaller is not installed. Installing it now...
    pip install pyinstaller
)

echo Clearing previous builds...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"

echo Installing requirements...
pip install -r requirements.txt

echo.
echo Creating executable...
pyinstaller --clean LightNovelScraper.spec

if %errorlevel% equ 0 (
    echo.
    echo Build successful! Executable is in the dist folder.
    echo Testing icon presence...
    powershell -Command "& {$icon = [System.Drawing.Icon]::ExtractAssociatedIcon('dist\LightNovelScraper.exe'); if ($icon) { echo 'Icon is present in the executable.' } else { echo 'Icon is missing from the executable.' }}"
) else (
    echo.
    echo Build failed or executable not found!
)
pause