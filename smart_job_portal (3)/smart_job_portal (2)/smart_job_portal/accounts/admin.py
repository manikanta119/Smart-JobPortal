from django.contrib import admin
from .models import UserProfile, Resume

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display  = ['user', 'role', 'location', 'created_at']
    list_filter   = ['role']
    search_fields = ['user__username', 'user__email']

@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display  = ['user', 'full_name', 'updated_at']
    search_fields = ['user__username', 'skills']
