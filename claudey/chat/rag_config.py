STOP_WORDS = {
    'nasıl', 'nedir', 'mi', 'mu', 'mı', 'var', 'için', 'ile', 've', 'bu',
    'bir', 'kim', 'nerede', 'ne', 'hakkında', 'hakkinda', 'kaç', 'hangi',
    'olan', 'olarak', 'daha', 'çok', 'az', 'ben', 'sen', 'siz', 'biz',
    'acıbadem', 'acibadem', 'üniversitesi', 'universitesi', 'bulunuyor',
    'bulunmakta', 'yer', 'alıyor', 'neden',
}

CHAT_KEYWORDS = {'merhaba', 'selam', 'hey', 'teşekkürler', 'teşekkür ederim', 'nasılsın', 'iyiyim'}

NOISY_URL_HINTS = ('/haberler/', '/duyurular/', '/etkinlikler/')

INTENT_HINTS = {
    'location': {'nerede', 'adres', 'ulaşım', 'ulasim', 'nasıl gidilir', 'nerede bulunuyor'},
    'contact': {'telefon', 'mail', 'e-posta', 'eposta', 'iletişim', 'iletisim', 'ulaşım', 'ulasim', 'adres'},
    'transport': {
        'nasıl ulaş', 'nasil ulas', 'ulaşabilirim', 'ulasabilirim', 'nasıl gidebilirim',
        'nasil gidebilirim', 'ulaşım', 'ulasim', 'metro', 'otobüs', 'otobus', 'durak',
    },
    'admission': {
        'başvuru', 'basvuru', 'kayıt', 'kayit', 'ücret', 'ucret', 'fiyat', 'burs',
        'kontenjan', 'puan', 'yatay geçiş', 'yatay gecis', 'dikey geçiş', 'dikey gecis',
    },
    'program': {
        'program', 'bölüm', 'bolum', 'mühendislik', 'muhendislik', 'fakülte', 'fakulte',
        'kaç yıl', 'kac yil', 'kaç sene', 'ders', 'müfredat', 'mufredat', 'akademik kadro',
    },
    'life': {
        'kampüste yaşam', 'kampuste yasam', 'yurt', 'konaklama', 'spor', 'kulüp', 'kulup',
        'erasmus', 'sağlık hizmetleri', 'saglik hizmetleri', 'kütüphane', 'kutuphane',
    },
}

INTENT_PRIORITY_FILTERS = {
    'contact': {'limit': 20},
    'admission': {'limit': 30},
    'program': {'limit': 40},
    'life': {'limit': 30},
}

INTENT_PROMPT_NOTES = {
    'transport': (
        "Kullanıcı ulaşım soruyor. Sadece verilen bağlamdaki ulaşım bilgisini kullan. "
        "Metro, durak, yürüyüş veya otobüs bilgisi varsa kısa ve doğal biçimde özetle. "
        "Bağlamda olmayan durak, hat veya otobüs numarası uydurma. "
        "Telefon, e-posta veya alakasız ek bilgi verme."
    ),
    'location': (
        "Kullanıcı adres/konum soruyor. Doğal, kısa ve tek cümlelik bir yanıt ver. "
        "Konumu doğrudan söyle. Gerekmedikçe 'adresi şöyledir' gibi resmi kalıplar kullanma. "
        "Telefon, e-posta, ulaşım tarifi veya başka ek bilgi verme. Cevabı kısa tut."
    ),
}
