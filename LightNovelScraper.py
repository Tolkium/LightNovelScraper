import requests
from bs4 import BeautifulSoup
from ebooklib import epub
from datetime import datetime
from collections import deque
import logging
import time
import re
from typing import Optional, Tuple, List, Dict, TypedDict, Union
from bs4.element import Comment
import os
from PIL import Image
from io import BytesIO
import platform
import argparse
from dataclasses import dataclass
from urllib.parse import urlparse

if  platform.system() == 'Windows':
    os.system('color')

class ChapterData(TypedDict):
    title: str
    content: str
    notes: List[str]
    footnotes: Dict[str, str]

@dataclass
class ScraperConstants:
    DEFAULT_TIMEOUT: int = 30
    MAX_RETRIES: int = 3
    MIN_CONTENT_LENGTH: int = 100
    DEFAULT_REQUESTS_PER_SECOND: float = 20.0
    MAX_COVER_HEIGHT: int = 2400
    COVER_ASPECT_RATIO: float = 2/3
    USER_AGENT: str = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

@dataclass
class Config:
    """Configuration settings for the scraper."""
    INCLUDE_FOOTNOTES: bool = False
    INCLUDE_CHAPTER_NOTES: bool = False
    SIMPLE_CHAPTER_NAMES: bool = False
    DEBUG_MODE: bool = False

    @classmethod
    def validate(cls) -> None:
        """Validate configuration settings."""
        if not all(isinstance(getattr(cls, attr), bool) for attr in cls.__annotations__):
            raise ValueError("All configuration values must be boolean")

class ConsoleColors:
    """ANSI color codes for console output."""
    RED: str = '\033[91m'
    GREEN: str = '\033[92m'
    YELLOW: str = '\033[93m'
    RESET: str = '\033[0m'

class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass

class ScraperError(Exception):
    """Custom exception for scraper-specific errors."""
    pass

class RateLimiter:
    """Rate limiting implementation with exponential backoff."""
   
    def __init__(self, requests_per_second: float = ScraperConstants.DEFAULT_REQUESTS_PER_SECOND):
        self.rate = requests_per_second
        self.min_interval = 1.0 / requests_per_second
        self.last_request_times = deque(maxlen=10)
        self.failed_attempts = 0
       
    def wait(self) -> None:
        """Wait appropriate time between requests with exponential backoff."""
        now = datetime.now()
        
        if self.last_request_times:
            elapsed = (now - self.last_request_times[-1]).total_seconds()
            wait_time = max(0, self.min_interval - elapsed)
        else:
            wait_time = 0

        if self.failed_attempts > 0:
            wait_time += min(300, (2 ** self.failed_attempts) - 1)
            
        if wait_time > 0:
            time.sleep(wait_time)
            
        self.last_request_times.append(now)
    
    def record_failure(self) -> None:
        self.failed_attempts += 1
    
    def record_success(self) -> None:
        self.failed_attempts = 0

class ProgressTracker:
    def __init__(self, total: int):
        self.total = total
        self.current = 0
        self.success = 0
        self.failures = 0
        
    def update(self, success: bool = True) -> None:
        self.current += 1
        if success:
            self.success += 1
        else:
            self.failures += 1
        self._display_progress()
    
    def _display_progress(self) -> None:
        percent = (self.current / self.total) * 100
        bar_length = 50
        filled_length = int(bar_length * self.current // self.total)
        bar = '=' * filled_length + '-' * (bar_length - filled_length)
        
        stats = f"Success: {self.success} Failures: {self.failures}"
        print(f'\rProgress |{bar}| {percent:.1f}% {stats}', end='', flush=True)

class LightNovelScraper:
    def __init__(self, debug_mode: bool = False):
        self._initialize_logging(debug_mode)
        self.headers = {'User-Agent': ScraperConstants.USER_AGENT}
        self.rate_limiter = RateLimiter()
        self.debug_mode = debug_mode
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def _initialize_logging(self, debug_mode: bool) -> None:
        log_level = logging.DEBUG if debug_mode else logging.INFO
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('scraper_detailed.log'),
                logging.StreamHandler() if debug_mode else logging.NullHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def validate_url(self, url: str) -> bool:
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception as e:
            self.logger.error(f"URL validation failed: {str(e)}")
            return False

    def get_cover_image(self, image_url: str) -> Optional[Tuple[bytes, str, str]]:
        if not self.validate_url(image_url):
            raise ValidationError("Invalid cover image URL")

        try:
            response = self.session.get(image_url, timeout=ScraperConstants.DEFAULT_TIMEOUT)
            response.raise_for_status()
            
            image = Image.open(BytesIO(response.content))
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            width, height = image.size
            target_ratio = ScraperConstants.COVER_ASPECT_RATIO
            current_ratio = width/height
            
            if current_ratio != target_ratio:
                if current_ratio > target_ratio:
                    new_width = int(height * target_ratio)
                    left = (width - new_width) // 2
                    image = image.crop((left, 0, left + new_width, height))
                else:
                    new_height = int(width / target_ratio)
                    top = (height - new_height) // 2
                    image = image.crop((0, top, width, top + new_height))
            
            if height > ScraperConstants.MAX_COVER_HEIGHT:
                new_height = ScraperConstants.MAX_COVER_HEIGHT
                new_width = int(new_height * target_ratio)
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            img_byte_arr = BytesIO()
            image.save(img_byte_arr, format='JPEG', quality=95)
            return img_byte_arr.getvalue(), 'image/jpeg', 'cover.jpg'
            
        except Exception as e:
            self.logger.error(f"Cover image processing failed: {str(e)}")
            return None

    def _clean_html_content(self, content_div: BeautifulSoup) -> BeautifulSoup:
        """Clean HTML content while preserving main content."""
        # Remove SSE comments and ad-related elements first
        content_str = str(content_div)
        content_str = re.sub(r'<!--sse-->.*?<!--/sse-->', '', content_str, flags=re.DOTALL)
        
        # Parse cleaned content back to BeautifulSoup
        content_div = BeautifulSoup(content_str, 'html.parser')
        
        # Remove specific ad-related elements
        for selector in [
            'script', '.CTGIiSmv', '.L-MHncuP', '.vm-placement', 
            'div[data-defid]', 'div[data-mobid]'
        ]:
            for element in content_div.select(selector):
                element.decompose()
        
        return content_div

    def _is_chapter_number(self, text: str) -> bool:
        text = text.strip()
        patterns = [
            r'^\d+$',
            r'^chapter\s+\d+$',
            r'^\d+\.?$'
        ]
        return any(re.match(pattern, text.lower()) for pattern in patterns)

    def _is_note_or_message(self, text: str, p_element: BeautifulSoup) -> bool:
        """Check if text or element content matches note patterns."""
        # First check strong/b elements combined with following text
        strong_elements = p_element.find_all(['strong', 'b'])
        for strong in strong_elements:
            strong_text = strong.text.strip().lower()
            if any(note_type in strong_text for note_type in [
                'translator\'s note', 'translator note',
                'chapter note', 't/n', 'note'
            ]):
                return True

        # Then check regular text patterns
        text_lower = text.lower()
        return any(pattern in text_lower for pattern in [
            't/n:', 'tn:', 't/l:', 'tl:',
            'translator\'s note:', 'translator note:',
            'chapter note:', 'chapter note by',
            'thanks for playing', 'as always'
        ])

    def _process_content(self, content_div: BeautifulSoup) -> Tuple[List[str], List[str], Dict[str, str], List[str]]:
        """Process and extract content components."""
        content_div = self._clean_html_content(content_div)
        
        paragraphs = []
        after_separator = []
        footnotes = {}
        debug_notes = []
        found_separator = False
        in_main_content = True
        
        if self.debug_mode:
            print("\nRaw content before processing:")
            print(content_div.prettify())
        
        for p in content_div.find_all('p'):
            text = p.text.strip()
            if not text:
                continue

            if self.debug_mode:
                print(f"\nProcessing paragraph: {text[:100]}...")

            # Always add to main content unless it's clearly a note
            if text.startswith('T/L:') or text.startswith('T/N:'):
                if Config.INCLUDE_CHAPTER_NOTES:
                    after_separator.append(str(p))
                debug_notes.append(f"Start note: {str(p)}")
                if self.debug_mode:
                    print("Found start note")
            elif text.startswith(tuple(str(i) + '.' for i in range(1, 10))) and ':' in text:
                if Config.INCLUDE_FOOTNOTES:
                    footnotes[text.split('.')[0]] = text
                debug_notes.append(f"Footnote: {text}")
                if self.debug_mode:
                    print("Found footnote")
            elif ('T/N:' in text or 'Chapter Note:' in text or 
                'Thanks for playing' in text or 'As always' in text or
                self._is_note_or_message(text, p)):
                found_separator = True
                if Config.INCLUDE_CHAPTER_NOTES:
                    after_separator.append(str(p))
                debug_notes.append(f"End note: {str(p)}")
                if self.debug_mode:
                    print("Found end note")
            else:
                # Add to main content if it's not obviously a note
                if not self._is_chapter_number(text):
                    paragraphs.append(str(p))
                    if self.debug_mode:
                        print("Added to main content")

        if self.debug_mode:
            print(f"\nProcessing results:")
            print(f"Main paragraphs: {len(paragraphs)}")
            print(f"After separator: {len(after_separator)}")
            print(f"Footnotes: {len(footnotes)}")
            print(f"Debug notes: {len(debug_notes)}")
            if len(paragraphs) > 0:
                print("\nFirst paragraph:")
                print(paragraphs[0])
                print("\nLast paragraph:")
                print(paragraphs[-1])

        return paragraphs, after_separator, footnotes, debug_notes

    def get_chapter_content(self, url: str) -> Tuple[Optional[str], Optional[str], Optional[List[str]], Optional[dict]]:
        """Fetch and process chapter content."""
        if not self.validate_url(url):
            raise ValidationError("Invalid chapter URL")

        for attempt in range(ScraperConstants.MAX_RETRIES):
            try:
                self.rate_limiter.wait()
                
                response = self.session.get(url, timeout=ScraperConstants.DEFAULT_TIMEOUT)
                response.raise_for_status()
                
                if not response.text.strip():
                    raise ValueError("Empty response received")
                
                # First parse the full HTML
                soup = BeautifulSoup(response.text, 'html.parser')
                
                title_elem = soup.find('span', class_='chapter-title')
                chapter_title = self._process_chapter_title(title_elem, url)
                
                if not chapter_title:
                    raise ValueError("Chapter title not found")

                # Find the chapter container and process its content
                content_div = soup.find('div', id='chapter-container')
                if not content_div:
                    raise ValueError("Content container not found")

                if self.debug_mode:
                    print(f"\nProcessing chapter: {chapter_title}")
                    print(f"URL: {url}")

                paragraphs, after_separator, footnotes, debug_notes = self._process_content(content_div)

                if len(paragraphs) == 0:
                    if self.debug_mode:
                        print("\nNo paragraphs found in content. Raw content:")
                        print(content_div.prettify())
                    raise ValueError("No valid content found")

                content = self._format_chapter_content(paragraphs, footnotes)
                
                if self.debug_mode and debug_notes:
                    print(f"\n{ConsoleColors.RED}Excluded notes for {chapter_title}:")
                    for note in debug_notes:
                        print(f"Note: {note}{ConsoleColors.RESET}")
                
                self.rate_limiter.record_success()
                return chapter_title, content, after_separator, footnotes

            except Exception as e:
                self.logger.error(f"Attempt {attempt + 1} failed for {url}: {str(e)}")
                if self.debug_mode:
                    import traceback
                    self.logger.error(traceback.format_exc())
                self.rate_limiter.record_failure()
                if attempt < ScraperConstants.MAX_RETRIES - 1:
                    time.sleep((attempt + 1) * 5)
                else:
                    return None, None, None, None

        return None, None, None, None

    def _process_chapter_title(self, title_elem: Optional[BeautifulSoup], url: str) -> Optional[str]:
        if not title_elem:
            return None
            
        if Config.SIMPLE_CHAPTER_NAMES:
            url_match = re.search(r'chapter-(\d+)', url)
            return f"Chapter {url_match.group(1)}" if url_match else title_elem.text.strip()
        return title_elem.text.strip()

    def _format_chapter_content(self, paragraphs: List[str], footnotes: Dict[str, str]) -> str:
        processed_paragraphs = []
        for p in paragraphs:
            if Config.INCLUDE_FOOTNOTES:
                soup_p = BeautifulSoup(p, 'html.parser')
                for sup in soup_p.find_all('sup'):
                    ref_num = sup.text.strip()
                    if ref_num in footnotes:
                        sup.wrap(soup_p.new_tag('a', href=f'#footnote-{ref_num}'))
                processed_paragraphs.append(str(soup_p))
            else:
                p_clean = re.sub(r'<sup>.*?</sup>', '', p)
                processed_paragraphs.append(p_clean)
        
        return "\n".join(processed_paragraphs)

class EpubCreator:
    def __init__(self, novel_title: str, author: str = "Unknown", 
                    translator: str = "", created_by: str = "LightNovelScraper"):
        self.novel_title = novel_title
        self.author = author
        self.translator = translator
        self.created_by = created_by
        self.book = epub.EpubBook()
        self._initialize_book()

    def _initialize_book(self) -> None:
        self.book.set_identifier(f'id_{self.novel_title.lower().replace(" ", "_")}')
        self.book.set_title(self.novel_title)
        self.book.set_language('en')
        
        if self.author and self.author != "Unknown":
            self.book.add_author(self.author)
        if self.translator:
            self.book.add_metadata('DC', 'contributor', self.translator, {'role': 'trl'})
        if self.created_by != "LightNovelScraper":
            self.book.add_metadata('DC', 'publisher', self.created_by)

    def add_cover(self, cover_data: Tuple[bytes, str, str]) -> None:
        image_data, content_type, image_name = cover_data
        self.book.set_cover(image_name, image_data)

    def add_chapter(self, chapter_data: ChapterData, index: int) -> epub.EpubHtml:
        chapter = epub.EpubHtml(
            title=chapter_data['title'],
            file_name=f'chap_{index:03d}.xhtml',
            lang='en'
        )
        
        chapter_content = [
            f'<h1>{chapter_data["title"]}</h1>',
            '<div class="chapter-content">',
            chapter_data['content']
        ]

        if Config.INCLUDE_FOOTNOTES and chapter_data['footnotes']:
            chapter_content.extend(self._format_footnotes(chapter_data['footnotes']))
            
        if Config.INCLUDE_CHAPTER_NOTES and chapter_data['notes']:
            chapter_content.extend(self._format_chapter_notes(chapter_data['notes']))
            
        chapter_content.append('</div>')
        chapter.content = '\n'.join(chapter_content)
        
        self.book.add_item(chapter)
        return chapter

    def _format_footnotes(self, footnotes: Dict[str, str]) -> List[str]:
        return [
            '<div class="footnotes">',
            '<hr/>',
            '<h3>Footnotes</h3>',
            *[f'<p id="footnote-{num}" class="footnote"><sup>{num}</sup> {text} '
                f'<a href="#ref-{num}">↩</a></p>'
                for num, text in footnotes.items()],
            '</div>'
        ]

    def _format_chapter_notes(self, notes: List[str]) -> List[str]:
        return [
            '<div class="chapter-notes">',
            '<hr/>',
            '<h3>Chapter Notes</h3>',
            *notes,
            '</div>'
        ]

    def finalize(self, chapters: List[epub.EpubHtml]) -> None:
        self._add_navigation(chapters)
        self._add_styling()
        self.book.spine = ['nav'] + chapters

    def _add_navigation(self, chapters: List[epub.EpubHtml]) -> None:
        self.book.toc = ((epub.Section(self.novel_title), chapters),)
        self.book.add_item(epub.EpubNcx())
        self.book.add_item(epub.EpubNav())

    def _add_styling(self) -> None:
        style = """
            body { 
                font-family: Times New Roman, serif; 
                margin: 5%; 
                text-align: justify; 
            }
            h1 { 
                text-align: center; 
                font-size: 2em;
                margin: 1em 0 2em 0;
            }
            h2 { margin-top: 2em; }
            h3 { margin-top: 1.5em; }
            p { margin: 1em 0; }
            .chapter-content {
                line-height: 1.6;
            }
            .footnotes {
                margin-top: 3em;
                font-size: 0.9em;
                border-top: 1px solid #cccccc;
                padding-top: 1em;
            }
            .footnote {
                margin: 0.5em 0;
                font-size: 0.9em;
            }
            .chapter-notes {
                margin-top: 3em;
                padding-top: 1em;
                border-top: 1px solid #ccc;
                font-size: 0.9em;
            }
            .note {
                font-style: italic;
                margin: 0.5em 0;
            }
            sup {
                vertical-align: super;
                font-size: 0.8em;
            }
            a {
                color: #000000;
                text-decoration: none;
            }
        """
        nav_css = epub.EpubItem(
            uid="style_nav",
            file_name="style/nav.css",
            media_type="text/css",
            content=style
        )
        self.book.add_item(nav_css)

def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Light Novel Scraper')
    
    required = parser.add_argument_group('required arguments')
    required.add_argument('--url', type=str, help='Base URL')
    required.add_argument('--novel-id', type=str, help='Novel ID')
    required.add_argument('--start', type=int, help='Start chapter')
    required.add_argument('--end', type=int, help='End chapter')
    required.add_argument('--title', type=str, help='Novel title')
    
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--cover-url', type=str, help='Cover image URL')
    parser.add_argument('--author', type=str, help='Author name')
    parser.add_argument('--translator', type=str, help='Translator name')
    parser.add_argument('--creator', type=str, help='Creator name')
    
    parser.add_argument('--simple-chapters', action='store_true', help='Use simple chapter numbering')
    parser.add_argument('--include-footnotes', action='store_true', help='Include footnotes')
    parser.add_argument('--include-notes', action='store_true', help='Include chapter notes')

    return parser.parse_args()

def get_yes_no_input(prompt: str, default: bool = False) -> bool:
    default_text = "Y/n" if default else "y/N"
    response = input(f"{prompt} ({default_text}): ").strip().lower()
    if not response:
        return default
    return response.startswith('y')

def get_optional_input(prompt: str, arg_value: Optional[str] = None, default: str = "") -> str:
    if arg_value is not None:
        return arg_value
    
    response = input(f"{prompt} (Enter to skip): ").strip()
    return response or default

def get_user_input(args: argparse.Namespace) -> Dict[str, str]:
    inputs = {}
    print("\nLight Novel Scraper")
    print("==================")

    inputs['base_url'] = args.url if args.url else input("\nEnter base URL: ").strip()
    if not inputs['base_url']:
        raise ValidationError("Base URL cannot be empty")
    if not inputs['base_url'].endswith('/'):
        inputs['base_url'] += '/'

    inputs['novel_id'] = args.novel_id if args.novel_id else input("Novel ID: ").strip()
    if not inputs['novel_id']:
        raise ValidationError("Novel ID cannot be empty")

    if args.start and args.end:
        inputs['start_chapter'] = args.start
        inputs['end_chapter'] = args.end
    else:
        try:
            inputs['start_chapter'] = int(input("Start chapter: "))
            inputs['end_chapter'] = int(input("End chapter: "))
            if inputs['start_chapter'] > inputs['end_chapter']:
                raise ValidationError("Start chapter cannot be greater than end chapter")
        except ValueError:
            raise ValidationError("Please enter valid chapter numbers")

    inputs['novel_title'] = args.title if args.title else input("Novel title: ").strip()
    if not inputs['novel_title']:
        raise ValidationError("Novel title cannot be empty")

    # Handle optional inputs based on whether they were provided as arguments
    if all([args.cover_url, args.author, args.translator, args.creator]):
        # If all optional arguments are provided, use them directly
        inputs['cover_url'] = args.cover_url
        inputs['author'] = args.author
        inputs['translator'] = args.translator
        inputs['created_by'] = args.creator
    else:
        # Only ask for inputs that weren't provided as arguments
        print("\nOptional Settings:")
        
        if args.cover_url is None:
            if get_yes_no_input("Add cover image?"):
                inputs['cover_url'] = get_optional_input("Cover image URL")
            else:
                inputs['cover_url'] = ""
        else:
            inputs['cover_url'] = args.cover_url

        if args.author is None:
            if get_yes_no_input("Add author?"):
                inputs['author'] = get_optional_input("Author name")
            else:
                inputs['author'] = ""
        else:
            inputs['author'] = args.author

        if args.translator is None:
            if get_yes_no_input("Add translator?"):
                inputs['translator'] = get_optional_input("Translator name")
            else:
                inputs['translator'] = ""
        else:
            inputs['translator'] = args.translator

        if args.creator is None:
            if get_yes_no_input("Change creator name?"):
                inputs['created_by'] = get_optional_input("Creator name", default="LightNovelScraper")
            else:
                inputs['created_by'] = "LightNovelScraper"
        else:
            inputs['created_by'] = args.creator

    if not any([args.simple_chapters, args.include_footnotes, args.include_notes]):
        print("\nConfiguration options:")
        Config.SIMPLE_CHAPTER_NAMES = get_yes_no_input("Use simple chapter numbering?")
        Config.INCLUDE_FOOTNOTES = get_yes_no_input("Include footnotes?")
        Config.INCLUDE_CHAPTER_NOTES = get_yes_no_input("Include chapter notes?")
    else:
        Config.SIMPLE_CHAPTER_NAMES = args.simple_chapters
        Config.INCLUDE_FOOTNOTES = args.include_footnotes
        Config.INCLUDE_CHAPTER_NOTES = args.include_notes

    return inputs

def main() -> None:
    try:
        args = parse_arguments()
        Config.DEBUG_MODE = args.debug

        inputs = get_user_input(args)

        print("\nFinal Configuration:")
        print(f"Base URL: {inputs['base_url']}")
        print(f"Novel ID: {inputs['novel_id']}")
        print(f"Chapters: {inputs['start_chapter']} to {inputs['end_chapter']}")
        print(f"Title: {inputs['novel_title']}")
        print(f"Debug Mode: {'On' if Config.DEBUG_MODE else 'Off'}")
        print(f"Simple Chapter Names: {'On' if Config.SIMPLE_CHAPTER_NAMES else 'Off'}")
        print(f"Include Footnotes: {'On' if Config.INCLUDE_FOOTNOTES else 'Off'}")
        print(f"Include Chapter Notes: {'On' if Config.INCLUDE_CHAPTER_NOTES else 'Off'}")
        
        if inputs['cover_url']:
            print(f"Cover URL: {inputs['cover_url']}")
        if inputs['author'] != "Unknown":
            print(f"Author: {inputs['author']}")
        if inputs['translator']:
            print(f"Translator: {inputs['translator']}")
        if inputs['created_by'] != "LightNovelScraper":
            print(f"Creator: {inputs['created_by']}")

        if not get_yes_no_input("\nProceed with these settings?", default=True):
            print("Aborted by user.")
            return

        scraper = LightNovelScraper(debug_mode=Config.DEBUG_MODE)
        progress = ProgressTracker(inputs['end_chapter'] - inputs['start_chapter'] + 1)
        
        chapters_data = []
        epub_creator = EpubCreator(
            inputs['novel_title'],
            author=inputs['author'],
            translator=inputs['translator'],
            created_by=inputs['created_by']
        )

        if inputs['cover_url']:
            cover_data = scraper.get_cover_image(inputs['cover_url'])
            if cover_data:
                epub_creator.add_cover(cover_data)
            else:
                print(f"\n{ConsoleColors.YELLOW}Warning: Failed to process cover image{ConsoleColors.RESET}")

        for chapter_num in range(inputs['start_chapter'], inputs['end_chapter'] + 1):
            url = f"{inputs['base_url']}{inputs['novel_id']}/chapter-{chapter_num}"
            
            chapter_title, content, notes, footnotes = scraper.get_chapter_content(url)
            
            if chapter_title and content:
                chapters_data.append({
                    'title': chapter_title,
                    'content': content,
                    'notes': notes or [],
                    'footnotes': footnotes or {}
                })
                progress.update(True)
            else:
                progress.update(False)
                print(f"\n{ConsoleColors.YELLOW}Warning: Failed to process chapter {chapter_num}{ConsoleColors.RESET}")

        if chapters_data:
            epub_chapters = []
            for idx, chapter_data in enumerate(chapters_data, 1):
                chapter = epub_creator.add_chapter(chapter_data, idx)
                epub_chapters.append(chapter)

            epub_creator.finalize(epub_chapters)
            epub_filename = f"{inputs['novel_title'].lower().replace(' ', '_')}.epub"
            
            try:
                epub.write_epub(epub_filename, epub_creator.book, {})
                print(f"\n{ConsoleColors.GREEN}Successfully created: {epub_filename}{ConsoleColors.RESET}")
                print(f"Total chapters: {len(chapters_data)}")
                print(f"Successful: {progress.success}")
                print(f"Failed: {progress.failures}")
            except Exception as e:
                print(f"\n{ConsoleColors.RED}Error creating EPUB file: {str(e)}{ConsoleColors.RESET}")
        else:
            print(f"\n{ConsoleColors.RED}No chapters were successfully scraped.{ConsoleColors.RESET}")

    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    except Exception as e:
        print(f"\n{ConsoleColors.RED}Error: {str(e)}{ConsoleColors.RESET}")
        if Config.DEBUG_MODE:
            import traceback
            print("\nFull error trace:")
            print(traceback.format_exc())

if __name__ == "__main__":
    main()