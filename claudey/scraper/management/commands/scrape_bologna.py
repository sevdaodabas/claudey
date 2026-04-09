import re
import time

import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand

from scraper.models import UniversityData

BOLOGNA_BASE = 'https://obs.acibadem.edu.tr/oibs/bologna/'

PROGRAM_TYPES = {
    'myo': 'Ön Lisans',
    'lis': 'Lisans',
    'yls': 'Yüksek Lisans',
    'dok': 'Doktora',
}

GENERAL_PAGES = {
    100: 'Yönetim',
    101: 'Üniversite Hakkında',
    102: 'Bologna Komisyonu',
    103: 'İletişim',
    104: 'AKTS Kataloğu',
    300: 'Şehir Hakkında',
    301: 'Kampüs',
    302: 'Yemek',
    303: 'Sağlık Hizmetleri',
    304: 'Spor ve Sosyal Yaşam',
    305: 'Öğrenci Kulüpleri',
    309: 'Konaklama',
    311: 'Engelli Öğrenci Hizmetleri',
    400: 'Bologna Süreci',
}

HEADERS = {
    'User-Agent': 'ACU-AI-Bot/1.0 (Akademik Proje)',
    'Accept-Language': 'tr-TR,tr;q=0.9',
}

NOISE_PATTERNS = [
    r'Cookie\s*(Policy|Politikası).*',
    r'Tüm [Hh]akları [Ss]aklıdır.*',
    r'Copyright\s*©.*',
]


def normalize_text(text):
    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    text = re.sub(r'\n\s*\n+', '\n\n', text)
    lines = [line.strip() for line in text.split('\n')]
    return '\n'.join(lines).strip()


def fetch_content(url):
    try:
        r = requests.get(url, timeout=15, headers=HEADERS)
        if r.status_code != 200:
            return ''
        soup = BeautifulSoup(r.text, 'lxml')
        if 'Sayfa Bulunamadı' in soup.get_text() or 'Page Not Found' in soup.get_text():
            return ''
        for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'noscript']):
            tag.decompose()
        for sidebar in soup.find_all('aside'):
            sidebar.decompose()
        for nav in soup.find_all(class_=re.compile(r'navbar|header')):
            nav.decompose()
        return normalize_text(soup.get_text(separator='\n'))
    except Exception:
        return ''


class Command(BaseCommand):
    help = 'Scrape ACU Bologna information system'

    def add_arguments(self, parser):
        parser.add_argument('--delay', type=float, default=1.5,
                            help='Delay between requests in seconds (default: 1.5)')

    def handle(self, *args, **options):
        delay = options['delay']
        saved = 0

        # General pages
        self.stdout.write("Scraping Bologna general pages...")
        for page_id, title in GENERAL_PAGES.items():
            url = f"{BOLOGNA_BASE}dynConPage.aspx?curPageId={page_id}&lang=tr"
            content = fetch_content(url)
            if content and len(content.strip()) >= 50:
                _, created = UniversityData.objects.update_or_create(
                    url=url,
                    defaults={
                        'title': title,
                        'content': content[:30000],
                        'category': 'general',
                        'source': 'bologna',
                        'level': '',
                    }
                )
                saved += 1
                status = "NEW" if created else "UPDATED"
                self.stdout.write(self.style.SUCCESS(f"  [{saved}] [{status}] {title}"))
            time.sleep(delay)

        # Program pages
        for type_code, level_name in PROGRAM_TYPES.items():
            self.stdout.write(f"\nScraping {level_name} programs...")
            list_url = f"{BOLOGNA_BASE}unitSelection.aspx?type={type_code}&lang=tr"
            try:
                r = requests.get(list_url, timeout=15, headers=HEADERS)
                soup = BeautifulSoup(r.text, 'lxml')
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    text = a.get_text(strip=True)
                    if 'curOp=showPac' in href and text:
                        match = re.search(r'curSunit=(\d+)', href)
                        if match:
                            sunit = match.group(1)
                            prog_url = f"{BOLOGNA_BASE}progAbout.aspx?lang=tr&curSunit={sunit}"
                            content = fetch_content(prog_url)
                            if content and len(content.strip()) >= 50:
                                _, created = UniversityData.objects.update_or_create(
                                    url=prog_url,
                                    defaults={
                                        'title': text[:300],
                                        'content': content[:30000],
                                        'category': 'program',
                                        'source': 'bologna',
                                        'level': level_name,
                                    }
                                )
                                saved += 1
                                status = "NEW" if created else "UPDATED"
                                self.stdout.write(self.style.SUCCESS(
                                    f"  [{saved}] [{status}] {text[:70]}"
                                ))
                            time.sleep(delay)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  Error: {e}"))

        self.stdout.write(self.style.SUCCESS(f"\nDone! {saved} Bologna pages saved"))
