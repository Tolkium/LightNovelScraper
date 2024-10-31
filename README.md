# Light Novel Scraper

A powerful tool to extract and convert light novels into EPUB format with support for footnotes, chapter notes, cover images, and more.

## Important Note

**Current Compatibility**: This tool was developed overnight while reading on a certain website where "lite" reading material exists in this "novel world" of ours 😉. World domination wasn't the goal - just wanted to enjoy some novels offline with my fancy TTS setup.

**Need help?** You have options:

1. Modify the content selectors yourself using the code comments below
2. Open an issue on GitHub - if I have time between reading chapters 📚, I might help adapt it

### For Developers

If you want to adapt this for a different site, you'll need to modify these parts in `LightNovelScraper.py`:

```python
# 1. Content targeting (required) - in get_chapter_content():
325  title_elem = soup.find('span', class_='chapter-title')  # Change this class
332  content_div = soup.find('div', id='chapter-container')  # Change this ID

# 2. Content cleaning (optional) - in _clean_html_content():
202  selectors = [ 'script' ..... 'div[data-mobid]' ]  # Remove or modify list
      
# 3. Content processing (optional) - in _process_content():
265 if text.startswith(('T/L:', 'T/N:'))  # Remove or modify translator notes at start
271 elif text.startswith(tuple(str(i) + '.' for i in range(1, 10))) and ':' in text  # Remove or modify footnotes
277 elif ('T/N:' in text or ..... self._is_note_or_message(text, p))  # Remove or modify end notes and messages
226 ['translator\'s note',  ..... 'note'] # Remove or modify strong text patterns
234 ['t/n:' ..... 'as always'] # Remove or modify regular text patterns

```

**Debug/Modify:**

```bash
python LightNovelScraper.py --debug  # See all processing details
```

Edit `_clean_html_content()` to modify content cleaning or `_process_content()` to change how special content (notes, footnotes) is handled.

**Please Note**: This is a hobby project created for legitimate use cases, such as:

- Using advanced Text-to-Speech solutions for personal audio enjoyment
- Reading offline during your commute

This is NOT a tool for commercial purposes or content redistribution. <span style="color: red; font-size: 1.2em">**Support the original content creators**</span> by visiting their sites and, if possible, purchasing official releases. Think of this as a personal format converter for your offline reading convenience.

## Features

- Downloads and converts light novels to EPUB format
- Customizable metadata (author, translator, creator)
- Cover image support with automatic resizing and optimization
- Footnotes support with proper linking
- Chapter notes support
- Simple chapter naming option
- Clean content filtering
- Progress tracking with real-time status
- Error handling and retry mechanism
- Rate limiting to prevent server overload
- Debug logging
- Cross-platform support (Windows, Linux, Mac)
- Command-line interface with both interactive and argument modes

## Requirements

- Python 3.7 or higher
- pip (Python package installer)

## Installation

1. Clone or download this repository
2. Navigate to the project directory
3. Run the installation script:

For Windows users:

```bash
run.bat
```

For Linux/Mac users:

```bash
chmod +x run.sh
./run.sh
```

## Usage

The script can be run in two modes:

Interactive Mode:

```bash
python LightNovelScraper.py
```

Command-line Mode:

```bash
python LightNovelScraper.py [options]
```

Command-line Options:

- `--url`: Base URL for the light novel website
- `--novel-id`: Novel ID from the URL
- `--start`: First chapter number to download
- `--end`: Last chapter number to download
- `--title`: Novel title for the EPUB file
- `--debug`: Enable debug mode
- `--cover-url`: Direct URL to cover image
- `--author`: Author name
- `--translator`: Translator name
- `--creator`: Creator name
- `--simple-chapters`: Use simple chapter numbering
- `--include-footnotes`: Include footnotes in output
- `--include-notes`: Include chapter notes in output

Example:

```bash
python LightNovelScraper.py --url "https://example.com/novel/" --novel-id "novel-name-123" --start 1 --end 10 --title "My Novel" --cover-url "https://example.com/cover.jpg" --author "Author Name" --simple-chapters
```

## Building Executable

To create a standalone executable:

For Windows:

```bash
build_exe.bat
```

For Linux/Mac:

```bash
chmod +x build_exe.sh
./build_exe.sh
```

## File Structure

```
project/
  ├── LightNovelScraper.py          # Main scraper script
  ├── lightnovelScraper_Simple.py   # Simplified version of scraper
  ├── requirements.txt              # Python dependencies
  ├── setup.py                      # Package setup file
  ├── build_exe.bat                 # Windows executable build script
  ├── build_exe.sh                  # Linux/Mac executable build script
  ├── build.bat                     # Windows build script
  ├── build.sh                      # Linux/Mac build script
  ├── run.bat                       # Windows run script
  ├── run.sh                        # Linux/Mac run script
  ├── icon.ico                      # Application icon
  ├── LightNovelScraper.spec        # PyInstaller spec file
  ├── README.md                     # Documentation
  ├── .gitignore                    # Git ignore file
  ├── build/                        # Build output directory
  └── dist/                         # Distribution output directory
```

## Advanced Features

- **Automatic Cover Processing**: Resizes and optimizes cover images to proper aspect ratio
- **Smart Content Filtering**: Removes ads and unwanted elements
- **Configurable Rate Limiting**: Prevents server overload
- **Progress Tracking**: Real-time progress display with success/failure counts
- **Error Recovery**: Automatic retry mechanism for failed downloads
- **Debug Logging**: Detailed logging for troubleshooting

## Troubleshooting

If you encounter issues:

1. Check your internet connection
2. Verify the Novel ID and URL are correct
3. Run with --debug flag for detailed logging
4. Check scraper_detailed.log for error messages
5. Ensure all dependencies are installed correctly
6. Try running with different rate limiting settings if experiencing timeouts

## Future Development Roadmap

### Maybe Implement in Future

- **Architecture**
  - Project code modularization

- **Basic GUI**
  - Simple application interface
  - Progress visualization

- **Content Targeting**
  - Configurable content selectors (CSS/class/ID)

- **Content Processing**
  - Better content cleaning

### Will See

- **Content Targeting**
  - Content boundary detection

- **Content Processing**
  - Better formatting preservation
  - Better metadata handling

### I Don't Think So

- **Architecture**
  - Plugin system for different sites
  - Transformation pipeline
  - Docker container
  - Machine learning features

Note: This roadmap reflects an honest assessment of future development possibilities. The "Maybe Implement in Future" features are those that could realistically be added if they prove necessary. "Will See" features depend on user feedback and project evolution. "I Don't Think So" acknowledges features that, while interesting, are likely beyond the scope of a single-developer hobby project.

## License

This project is for educational purposes only. Use responsibly and in accordance with the terms of service of the target websites.
