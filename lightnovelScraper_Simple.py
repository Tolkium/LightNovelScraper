import requests
from bs4 import BeautifulSoup
import ebooklib
from ebooklib import epub
from datetime import datetime
from collections import deque
import logging
import sys
import time
import re
from typing import Optional, Tuple, List
from bs4.element import Comment
import os

# Global Configuration
class Config:
    INCLUDE_FOOTNOTES = False  # Toggle for footnotes in chapters
    INCLUDE_CHAPTER_NOTES = False  # Toggle for content after || separator
    SIMPLE_CHAPTER_NAMES = False  # Toggle for simplified chapter names (Chapter X)
    DEBUG_MODE = False

class RateLimiter:
    def __init__(self, requests_per_second=2):
        self.rate = requests_per_second
        self.min_interval = 1.0 / requests_per_second
        self.last_request_times = deque(maxlen=10)
        
    def wait(self):
        now = datetime.now()
        if self.last_request_times:
            elapsed = (now - self.last_request_times[-1]).total_seconds()
            if elapsed < self.min_interval:
                sleep_time = max(0, self.min_interval - elapsed)
                time.sleep(sleep_time)
        self.last_request_times.append(now)

class LightNovelScraper:
    def __init__(self, debug_mode=False):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.base_url = "https://www.lightnovelworld.co/novel/"
        self.rate_limiter = RateLimiter(requests_per_second=2)
        self.debug_mode = debug_mode
        
        logging.basicConfig(
            level=logging.DEBUG if debug_mode else logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('scraper_detailed.log'),
                logging.StreamHandler() if debug_mode else logging.NullHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        self.consecutive_failures = 0
        self.max_retries = 3
        self.min_content_length = 100

    def get_chapter_content(self, url: str) -> Tuple[Optional[str], Optional[str], Optional[List[str]], Optional[dict]]:
        for attempt in range(self.max_retries):
            try:
                self.rate_limiter.wait()
                
                self.logger.info(f"Fetching URL: {url}")
                response = requests.get(url, headers=self.headers, timeout=30)
                
                response.raise_for_status()
                
                if not response.text.strip():
                    self.logger.error(f"Empty response received for {url}")
                    raise ValueError("Empty response received from server")
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Find chapter title
                chapter_title = None
                title_elem = soup.find('span', class_='chapter-title')
                if title_elem:
                    if Config.SIMPLE_CHAPTER_NAMES:
                        # Use only the chapter number from URL
                        url_match = re.search(r'chapter-(\d+)', url)
                        if url_match:
                            chapter_num = url_match.group(1)
                            chapter_title = f"Chapter {chapter_num}"
                        else:
                            chapter_title = title_elem.text.strip()
                    else:
                        chapter_title = title_elem.text.strip()

                if not chapter_title:
                    self.logger.warning(f"No chapter title found for {url}")
                    return None, None, None, None
                
                # Find content
                content_div = soup.find('div', id='chapter-container')
                if not content_div:
                    self.logger.warning(f"No content container found for {url}")
                    return None, None, None, None
                
                # Clean up content
                for element in content_div.select('script, ins, iframe, .adsbox, .ads, .ad-container, .aoyveLDZ, .vm-placement, div[data-defid]'):
                    element.decompose()
                
                # Extract paragraphs, notes and footnotes
                paragraphs = []
                after_separator = []
                footnotes = {}
                found_first_separator = False
                in_main_content = True
                
                for p in content_div.find_all('p'):
                    text = p.text.strip()
                    if text:
                        # Check for separator
                        if text == '||':
                            if not found_first_separator:
                                found_first_separator = True
                                continue
                            else:
                                in_main_content = False
                                continue
                        
                        if in_main_content:
                            # Add main content
                            paragraphs.append(str(p))
                        else:  # After || separator
                            # Check if it's a footnote
                            if '↩' in text and Config.INCLUDE_FOOTNOTES:
                                footnote_refs = p.find_all('sup')
                                for ref in footnote_refs:
                                    ref_num = ref.text.strip()
                                    if ref_num not in footnotes:  # Avoid duplicates
                                        footnotes[ref_num] = text
                            # If not a footnote and chapter notes are enabled, add to after_separator
                            elif Config.INCLUDE_CHAPTER_NOTES:
                                after_separator.append(text)
                if not paragraphs:
                    self.logger.warning(f"No valid paragraphs found for {url}")
                    return None, None, None, None
                
                # Process main content to add footnote links if enabled
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
                        # Remove sup tags if footnotes are disabled
                        p_clean = re.sub(r'<sup>.*?</sup>', '', p)
                        processed_paragraphs.append(p_clean)
                
                # Join paragraphs with proper HTML
                content = "\n".join(processed_paragraphs)
                
                return chapter_title, content, after_separator, footnotes
                
            except Exception as e:
                self.logger.error(f"Error processing {url}: {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep((attempt + 1) * 5)
                else:
                    return None, None, None, None
        
        return None, None, None, None

    def create_epub(self, novel_title: str, chapters_data: List[Tuple[str, str, List[str], dict]]) -> Optional[epub.EpubBook]:
        try:
            book = epub.EpubBook()
            
            book.set_identifier(f'id_{novel_title.lower().replace(" ", "_")}')
            book.set_title(novel_title)
            book.set_language('en')
            book.add_author('LightNovelScraper')

            chapters = []
            chapter_entries = []

            for idx, (chapter_title, content, after_separator, footnotes) in enumerate(chapters_data, 1):
                chapter = epub.EpubHtml(
                    title=chapter_title,
                    file_name=f'chap_{idx:03d}.xhtml',
                    lang='en'
                )
                
                chapter_content = [
                    f'<h1>{chapter_title}</h1>',
                    '<div class="chapter-content">',
                    content
                ]
                
                # Add footnotes if enabled and present
                if Config.INCLUDE_FOOTNOTES and footnotes:
                    chapter_content.append('<div class="footnotes">')
                    chapter_content.append('<hr/>')
                    chapter_content.append('<h3>Footnotes</h3>')
                    for num, text in footnotes.items():
                        chapter_content.append(
                            f'<p id="footnote-{num}" class="footnote">'
                            f'<sup>{num}</sup> {text} '
                            f'<a href="#ref-{num}">↩</a></p>'
                        )
                    chapter_content.append('</div>')
                
                # Only add chapter notes if explicitly enabled
                if Config.INCLUDE_CHAPTER_NOTES and after_separator and len(after_separator) > 0:
                    chapter_content.append('<div class="chapter-notes">')
                    chapter_content.append('<hr/>')
                    chapter_content.append('<h3>Chapter Notes</h3>')
                    for note in after_separator:
                        chapter_content.append(f'<p class="note">{note}</p>')
                    chapter_content.append('</div>')
                
                chapter_content.append('</div>')
                chapter.content = '\n'.join(chapter_content)
                
                book.add_item(chapter)
                chapters.append(chapter)
                chapter_entries.append(chapter)

            # Define Table of Contents
            book.toc = ((epub.Section(novel_title), chapter_entries),)

            # Add navigation files
            book.add_item(epub.EpubNcx())
            book.add_item(epub.EpubNav())

            # Define CSS
            style = """
                body { 
                    font-family: Times New Roman, serif; 
                    margin: 5%; 
                    text-align: justify; 
                }
                h1 { text-align: center; }
                h2 { margin-top: 2em; }
                h3 { margin-top: 1.5em; }
                p { margin: 1em 0; }
                .footnotes {
                    margin-top: 3em;
                    font-size: 0.9em;
                }
                .footnote {
                    margin: 0.5em 0;
                }
                .chapter-notes {
                    margin-top: 3em;
                    padding-top: 1em;
                    border-top: 1px solid #ccc;
                }
                .note {
                    font-style: italic;
                    margin: 0.5em 0;
                }
                sup {
                    vertical-align: super;
                    font-size: 0.8em;
                }
            """
            nav_css = epub.EpubItem(
                uid="style_nav",
                file_name="style/nav.css",
                media_type="text/css",
                content=style
            )
            book.add_item(nav_css)

            # Set spine
            book.spine = ['nav'] + chapters

            return book

        except Exception as e:
            self.logger.error(f"Error creating EPUB: {str(e)}")
            return None

def main():
    # Set debug mode
    Config.DEBUG_MODE = "--debug" in sys.argv
    scraper = LightNovelScraper(debug_mode=Config.DEBUG_MODE)
    
    # Allow command line arguments for footnotes and chapter notes
    Config.INCLUDE_FOOTNOTES = "--no-footnotes" not in sys.argv
    Config.INCLUDE_CHAPTER_NOTES = "--no-chapter-notes" not in sys.argv
    Config.SIMPLE_CHAPTER_NAMES = "--simple-chapters" in sys.argv
    
    try:
        print("Light Novel Scraper")
        print(f"[Settings: Footnotes: {'On' if Config.INCLUDE_FOOTNOTES else 'Off'}, "
              f"Notes: {'On' if Config.INCLUDE_CHAPTER_NOTES else 'Off'}, "
              f"Simple Chapter Names: {'On' if Config.SIMPLE_CHAPTER_NAMES else 'Off'}]")
        
        novel_id = input("Novel ID: ").strip()
        if not novel_id:
            raise ValueError("Novel ID cannot be empty")
            
        try:
            start_chapter = int(input("Start chapter: "))
            end_chapter = int(input("End chapter: "))
            if start_chapter > end_chapter:
                raise ValueError("Start chapter cannot be greater than end chapter")
        except ValueError as e:
            raise ValueError("Please enter valid chapter numbers")
            
        novel_title = input("Novel title: ").strip()
        if not novel_title:
            raise ValueError("Novel title cannot be empty")
        
        chapters_data = []
        successful_requests = 0
        total_requests = 0
        
        for chapter_num in range(start_chapter, end_chapter + 1):
            url = f"{scraper.base_url}{novel_id}/chapter-{chapter_num}"
            print(f"\rProcessing: Chapter {chapter_num}/{end_chapter}...", end="", flush=True)
            
            chapter_title, content, after_separator, footnotes = scraper.get_chapter_content(url)
            total_requests += 1
            
            if chapter_title and content:
                chapters_data.append((chapter_title, content, after_separator, footnotes))
                successful_requests += 1
            else:
                print(f"\nFailed: Chapter {chapter_num}")
        
        if chapters_data:
            book = scraper.create_epub(novel_title, chapters_data)
            
            if book:
                epub_filename = f"{novel_title.lower().replace(' ', '_')}.epub"
                try:
                    epub.write_epub(epub_filename, book, {})
                    print(f"\nCreated: {epub_filename}")
                    
                except Exception as e:
                    print(f"\nError creating EPUB: {str(e)}")
                    if Config.DEBUG_MODE:
                        import traceback
                        print(traceback.format_exc())
        else:
            print("\nNo chapters were scraped successfully.")
            
    except Exception as e:
        print(f"\nError: {str(e)}")
        if Config.DEBUG_MODE:
            import traceback
            print(traceback.format_exc())

if __name__ == "__main__":
    main()