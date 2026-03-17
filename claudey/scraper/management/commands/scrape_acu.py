import time
import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from scraper.models import UniversityData

class Command(BaseCommand):
    help = 'Scrape data from ACU website'

    def handle(self, *args, **kwargs):

        urls = ["https://www.acibadem.edu.tr",
                "https://acibadem.edu.tr/universite",
                "https://acibadem.edu.tr/universite/hakkinda/misyon-vizyon-temel-degerler",
                "https://acibadem.edu.tr/universite/hakkinda/neden-acu",
                "https://acibadem.edu.tr/universite/hakkinda/universite-yonetimi",
                "https://acibadem.edu.tr/akademik/lisans/muhendislik-ve-doga-bilimleri-fakultesi",
                "https://acibadem.edu.tr/academic/undergraduate-programs/faculty-of-engineering-and-natural-sciences/about-faculty",
                "https://acibadem.edu.tr/akademik/lisans/muhendislik-ve-doga-bilimleri-fakultesi/vizyon-misyon",
                "https://acibadem.edu.tr/akademik/lisans/muhendislik-ve-doga-bilimleri-fakultesi/dekanlik",
                "https://acibadem.edu.tr/akademik/lisans/muhendislik-ve-doga-bilimleri-fakultesi/yonetim",
                "https://acibadem.edu.tr/akademik/lisans/muhendislik-ve-doga-bilimleri-fakultesi/akademik-kadro",
                "https://acibadem.edu.tr/akademik/lisans/muhendislik-ve-doga-bilimleri-fakultesi/bolumler/bilgisayar-muhendisligi",
                "https://acibadem.edu.tr/akademik/lisans/muhendislik-ve-doga-bilimleri-fakultesi/bolumler/bilgisayar-muhendisligi/bolum-baskaninin-mesaji",
                "https://acibadem.edu.tr/akademik/lisans/muhendislik-ve-doga-bilimleri-fakultesi/bolumler/bilgisayar-muhendisligi/hakkinda",
                "https://acibadem.edu.tr/akademik/lisans/muhendislik-ve-doga-bilimleri-fakultesi/bolumler/bilgisayar-muhendisligi/komisyonlar",
                "https://acibadem.edu.tr/akademik",
                "https://acibadem.edu.tr/ogrenci/odeme-yontemleri",
                "https://acibadem.edu.tr/ogrenci/acuda-yasam/ogrenci-kulupleri",
                "https://acibadem.edu.tr/ogrenci/acuda-yasam/ulasim",
                "https://acibadem.edu.tr/ogrenci/acuda-yasam/acibadem-mehmet-ali-aydinlar-universitesi-ogrenci-yurtlari/hakkinda",
                "https://acibadem.edu.tr/ogrenci/acuda-yasam/acibadem-mehmet-ali-aydinlar-universitesi-ogrenci-yurtlari/iletisim",
                "https://acibadem.edu.tr/oryantasyon-2022/sikca-sorulan-sorular",
                "https://acibadem.edu.tr/oryantasyon-2022/birimlere-nasil-ulasirim",
                "https://acibadem.edu.tr/aday/ogrenci/egitim/lisans/lisans-kontenjan-ve-puan-tablosu",
                "https://acibadem.edu.tr/akademik/ortak-dersler-bolumleri/yabanci-diller/ingilizce-hazirlik-programi/program-hakkinda",
                "https://acibadem.edu.tr/akademik/ortak-dersler-bolumleri/yabanci-diller/ingilizce-hazirlik-programi/program-hakkinda",
                "https://acibadem.edu.tr/akademik/rektorluge-bagli-bolumler/yabanci-diller/ingilizce-hazirlik-programi/egitim-felsefemiz",
                "https://acibadem.edu.tr/akademik/rektorluge-bagli-bolumler/yabanci-diller/ingilizce-hazirlik-programi/seviyeler-ve-dersler",
                "https://acibadem.edu.tr/akademik/rektorluge-bagli-bolumler/yabanci-diller/ingilizce-hazirlik-programi/muafiyet",
                "https://acibadem.edu.tr/akademik/rektorluge-bagli-bolumler/yabanci-diller/ingilizce-hazirlik-programi/komite-ve-birimler",
                "https://acibadem.edu.tr/akademik/rektorluge-bagli-bolumler/yabanci-diller/ingilizce-hazirlik-programi/yaz-donemi",
                "https://acibadem.edu.tr/akademik/rektorluge-bagli-bolumler/yabanci-diller/ingilizce-hazirlik-programi/akademik-kadro",
                "https://acibadem.edu.tr/akademik/rektorluge-bagli-bolumler/yabanci-diller/ingilizce-hazirlik-programi/akademik-takvim",
                "https://acibadem.edu.tr/aday/ogrenci/egitim/burs/burs-olanaklari",
                "https://acibadem.edu.tr/aday/ogrenci/egitim/burs/egitim-bursu",
                "https://acibadem.edu.tr/uluslararasi-ofis/degisim-programlari/erasmus/ogrenci-hareketliligi",
                "https://acibadem.edu.tr/uluslararasi-ofis/degisim-programlari/erasmus/ikili-anlasmalar",
                "https://acibadem.edu.tr/uluslararasi-ofis/degisim-programlari/erasmus/koordinatorler-listesi",
                "https://acibadem.edu.tr/uluslararasi-ofis/degisim-programlari/erasmus/degisim-programlari-gerekli-belgeler",
                "https://acibadem.edu.tr/akademik/lisans/tip-fakultesi/hakkinda",
                "https://acibadem.edu.tr/akademik/lisans/tip-fakultesi/temel-tip-bilimleri",
                "https://acibadem.edu.tr/akademik/lisans/tip-fakultesi/bolumler/dahili-tip-bilimleri",
                "https://acibadem.edu.tr/akademik/lisans/tip-fakultesi/bolumler/cerrahi-tip-bilimleri",
                "https://acibadem.edu.tr/akademik/lisans/eczacilik-fakultesi/hakkinda",
                "https://acibadem.edu.tr/akademik/lisans/eczacilik-fakultesi/eczacilik-fakultesi",
                "https://acibadem.edu.tr/akademik/lisans/saglik-bilimleri-fakultesi",
                "https://acibadem.edu.tr/akademik/lisans/saglik-bilimleri-fakultesi/fakulte-hakkinda",
                "https://acibadem.edu.tr/akademik/lisans/insan-ve-toplum-bilimleri-fakultesi/insan-ve-toplum-bilimleri-fakultesi",
                "https://acibadem.edu.tr/akademik/lisans/insan-ve-toplum-bilimleri-fakultesi/bolumler/psikoloji",
                "https://acibadem.edu.tr/akademik/lisans/insan-ve-toplum-bilimleri-fakultesi/bolumler/psikoloji-en/psikoloji-ingilizce",
                "https://acibadem.edu.tr/akademik/lisans/insan-ve-toplum-bilimleri-fakultesi/bolumler/sosyoloji/sosyoloji",
                "https://acibadem.edu.tr/akademik/lisans/muhendislik-ve-doga-bilimleri-fakultesi/bolumler/molekuler-biyoloji-ve-genetik",
                ]

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
            'Referer': 'https://www.google.com/'
        }
        
        for url in urls:

            self.stdout.write(self.style.SUCCESS(f"Processing {url}..."))

            try:
                
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, 'html.parser')

                title = soup.title.string.strip() if soup.title else 'No Title'

                for tag in soup(['script', 'style', "nav", "footer", "header"]):
                    tag.extract()

                raw_text = soup.get_text(separator=' ', strip=True)
                cleaned_text = ' '.join(raw_text.split())

                cleaned_text = cleaned_text[:30000]

                _, created = UniversityData.objects.update_or_create(
                    url=url,
                    defaults={'title': title, 'content': cleaned_text}
                )

                if created:
                    self.stdout.write(self.style.SUCCESS(f"New record for {url} created successfully."))
                else:
                    self.stdout.write(self.style.SUCCESS(f"Record for {url} updated successfully."))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error scraping {url}: {e}"))
            
            time.sleep(2)
