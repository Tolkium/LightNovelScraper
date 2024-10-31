# setup.py
from setuptools import setup, find_packages

setup(
    name="LightNovelScraper",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        'requests>=2.31.0',
        'beautifulsoup4>=4.12.0',
        'EbookLib>=0.18.0',
        'Pillow>=10.0.0',
    ],
    entry_points={
        'console_scripts': [
            'lightnovelscraper=LightNovelScraper:main',
        ],
    },
    author="Your Name",
    author_email="your.email@example.com",
    description="A tool for scraping light novels and converting them to EPUB format",
    long_description=open('README.md').read(),
    long_description_content_type="text/markdown",
    keywords="light novel, scraper, epub, ebook",
    url="https://github.com/yourusername/LightNovelScraper",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.7',
)