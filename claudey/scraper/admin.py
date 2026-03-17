from django.contrib import admin
from .models import UniversityData

@admin.register(UniversityData)
class UniversityDataAdmin(admin.ModelAdmin):
    list_display = ('title', 'url', 'scraped_at')
    search_fields = ('title', 'content')