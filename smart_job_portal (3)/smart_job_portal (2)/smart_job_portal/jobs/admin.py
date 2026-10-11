from django.contrib import admin
from .models import JobPost, Application

@admin.register(JobPost)
class JobPostAdmin(admin.ModelAdmin):
    list_display  = ['title', 'company', 'location', 'job_type', 'status', 'created_at']
    list_filter   = ['status', 'job_type', 'experience_level']
    search_fields = ['title', 'company', 'required_skills']
    date_hierarchy = 'created_at'

@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display  = ['applicant', 'job', 'status', 'match_score', 'applied_at']
    list_filter   = ['status']
    search_fields = ['applicant__username', 'job__title']
