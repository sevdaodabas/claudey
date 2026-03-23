import re
import time
from collections import deque
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand

from scraper.models import UniversityData

MAIN_SITE_SEEDS = [
    'https://www.acibadem.edu.tr/',
    'https://www.acibadem.edu.tr/akademik',
    'https://www.acibadem.edu.tr/akademik/lisans',
    'https://www.acibadem.edu.tr/akademik/onlisans',
    'https://www.acibadem.edu.tr/akademik/lisansustu',
    'https://www.acibadem.edu.tr/aday/ogrenci',
    'https://www.acibadem.edu.tr/ogrenci/acuda-yasam',
    'https://www.acibadem.edu.tr/arastirma',
    'https://www.acibadem.edu.tr/iletisim',
    'https://www.acibadem.edu.tr/kariyer-merkezi',
]

SKIP_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico',
    '.mp4', '.mp3', '.zip', '.rar', '.css', '.js',
}

SKIP_PATTERNS = [
    '/en/', '/en?', 'lang=en', '/search', '/login', '/admin',
    '/user/', '/print/', '/feed/', '#', 'javascript:', 'mailto:', 'tel:',
]

CATEGORY_KEYWORDS = {
    'program': ['fakulte', 'bolum', 'program', 'lisans', 'akademik/lisans', 'akademik/onlisans'],
    'admission': ['aday', 'basvur', 'kabul', 'kayit', 'kontenjan', 'puan'],
    'course': ['ders', 'mufredat'],
    'staff': ['personel', 'akademik-kadro', 'ogretim'],
    'contact': ['iletisim', 'ulasim'],
    'general': ['hakkimizda', 'hakkinda', 'kampus', 'acuda-yasam', 'ogrenci', 'burs',
                'kariyer', 'arastirma', 'kutuphane', 'yurt', 'spor', 'kulup'],
}

NOISE_PATTERNS = [
    r'Cookie\s*(Policy|Politikası).*',
    r'Tüm [Hh]akları [Ss]aklıdır.*',
    r'All [Rr]ights [Rr]eserved.*',
    r'Copyright\s*©.*',
    r'Gizlilik\s*(Politikası|Sözleşmesi).*',
    r'Ana\s*Sayfa\s*>\s*',
    r'Skip to (main )?content',
]

HEADERS = {
    'User-Agent': 'ACU-AI-Bot/1.0 (Akademik Proje)',
    'Accept-Language': 'tr-TR,tr;q=0.9',
    'Accept': 'text/html,application/xhtml+xml',
}


def normalize_text(text):
    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    text = re.sub(r'\n\s*\n+', '\n\n', text)
    lines = [line.strip() for line in text.split('\n')]
    return '\n'.join(lines).strip()


def extract_title(soup, url):
    if soup.title and soup.title.string:
        title = soup.title.string.strip().split('|')[0].strip()
        if title:
            return title[:300]
    h1 = soup.find('h1')
    if h1:
        return h1.get_text(strip=True)[:300]
    return urlparse(url).path.strip('/').split('/')[-1].replace('-', ' ').title()[:300]


def extract_main_content(soup):
    for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'header', 'noscript', 'iframe']):
        tag.decompose()
    for el in soup.find_all(class_=re.compile(
        r'cookie|popup|modal|overlay|banner|advertisement|sidebar|menu|nav', re.I
    )):
        el.decompose()
    main = (
        soup.find('main') or
        soup.find('article') or
        soup.find('div', class_=re.compile(r'content|main|body|article', re.I)) or
        soup.find('div', id=re.compile(r'content|main|body', re.I)) or
        soup.body
    )
    if not main:
        return ''
    return normalize_text(main.get_text(separator='\n'))


def guess_category(url):
    url_lower = url.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in url_lower for kw in keywords):
            return category
    return 'other'


def should_skip_url(url):
    parsed = urlparse(url)
    if any(parsed.path.lower().endswith(ext) for ext in SKIP_EXTENSIONS):
        return True
    return any(pattern in url for pattern in SKIP_PATTERNS)


class Command(BaseCommand):
    help = 'Scrape ACU main website using BFS crawling'

    def add_arguments(self, parser):
        parser.add_argument('--max-pages', type=int, default=100,
                            help='Maximum number of pages to scrape (default: 100)')
        parser.add_argument('--delay', type=float, default=1.0,
                            help='Delay between requests in seconds (default: 1.0)')

    def handle(self, *args, **options):
        max_pages = options['max_pages']
        delay = options['delay']

        self.stdout.write(f"BFS scraping starting... (limit: {max_pages}, delay: {delay}s)")

        queue = deque(MAIN_SITE_SEEDS)
        visited = set()
        saved = 0

        while queue and saved < max_pages:
            url = queue.popleft()
            if url in visited:
                continue
            visited.add(url)
            if should_skip_url(url):
                continue
            parsed = urlparse(url)
            if parsed.netloc not in ('www.acibadem.edu.tr', 'acibadem.edu.tr'):
                continue

            try:
                response = requests.get(url, timeout=15, headers=HEADERS)
                if response.status_code != 200:
                    continue
                if 'text/html' not in response.headers.get('Content-Type', ''):
                    continue

                soup = BeautifulSoup(response.text, 'lxml')
                title = extract_title(soup, url)
                content = extract_main_content(soup)

                if not content or len(content.strip()) < 80:
                    continue
                alpha_chars = sum(1 for c in content if c.isalpha())
                if alpha_chars < 20:
                    continue

                category = guess_category(url)

                _, created = UniversityData.objects.update_or_create(
                    url=url,
                    defaults={
                        'title': title,
                        'content': content[:30000],
                        'category': category,
                        'source': 'main_site',
                        'level': '',
                    }
                )

                saved += 1
                status = "NEW" if created else "UPDATED"
                self.stdout.write(self.style.SUCCESS(f"  [{saved:3d}] [{status}] {title[:70]}"))

                for link in soup.find_all('a', href=True):
                    full_url = urljoin(url, link['href']).split('#')[0].split('?')[0]
                    if full_url not in visited:
                        queue.append(full_url)

                time.sleep(delay)

            except requests.exceptions.RequestException:
                continue
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  Error: {url} -- {e}"))

        self.stdout.write(self.style.SUCCESS(
            f"\nDone! {saved} pages saved ({len(visited)} URLs visited)"
        ))
