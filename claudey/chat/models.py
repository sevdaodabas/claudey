from django.db import models

class UniversityData(models.Model):
    url = models.URLField(unique=True)
    title = models.CharField(max_length=255)
    content = models.TextField()
    scraped_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "University Data"
        verbose_name_plural = "University Data"

    def __str__(self):
        return self.title or self.url

class ChatMessage(models.Model):
    user_query = models.TextField()
    ai_response = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    
