from django.db import models

class UniversityData(models.Model):
    url = models.URLField(unique=True, help_text="URL of the university's page where data was scraped.")
    title = models.CharField(max_length=255, help_text="Title of the page.")
    content = models.TextField(help_text="Content of the page.")
    scraped_at = models.DateTimeField(auto_now_add=True, help_text="Timestamp when the data was scraped.")

    class Meta:
        verbose_name = "University Data"
        verbose_name_plural = "University Data"

    def __str__(self):
        return self.title or self.url