from django.db import models


class UniversityData(models.Model):
    CATEGORY_CHOICES = [
        ('program', 'Program'),
        ('course', 'Course'),
        ('general', 'General'),
        ('admission', 'Admission'),
        ('staff', 'Staff'),
        ('contact', 'Contact'),
        ('other', 'Other'),
    ]
    SOURCE_CHOICES = [
        ('main_site', 'Main Site'),
        ('bologna', 'Bologna'),
    ]

    url = models.URLField(unique=True)
    title = models.CharField(max_length=300)
    content = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='main_site')
    level = models.CharField(max_length=50, blank=True, default='')
    scraped_at = models.DateTimeField(auto_now_add=True)
    # Vektör indeksi ile DB'yi senkron tutmak için son indexlenen içeriğin SHA256'sı.
    # Reindex sırasında bu alan güncellenir; eşleşiyorsa o kayıt yeniden embed edilmez.
    content_hash = models.CharField(max_length=64, blank=True, default='', db_index=True)

    class Meta:
        verbose_name = "University Data"
        verbose_name_plural = "University Data"

    def __str__(self):
        return self.title or self.url