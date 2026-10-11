from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('jobseeker', 'Job Seeker'),
        ('employer', 'Employer'),
    ]
    user       = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role       = models.CharField(max_length=20, choices=ROLE_CHOICES, default='jobseeker')
    phone      = models.CharField(max_length=15, blank=True)
    location   = models.CharField(max_length=100, blank=True)
    bio        = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} ({self.role})"


class Resume(models.Model):
    user        = models.OneToOneField(User, on_delete=models.CASCADE, related_name='resume')
    full_name   = models.CharField(max_length=200, blank=True)
    skills      = models.TextField(blank=True, help_text="Comma-separated skills e.g. Python, Django, SQL")
    experience  = models.TextField(blank=True, help_text="Work experience details")
    education   = models.TextField(blank=True, help_text="Education details")
    certifications = models.TextField(blank=True)
    linkedin_url   = models.URLField(blank=True)
    github_url     = models.URLField(blank=True)
    updated_at  = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Resume of {self.user.username}"

    def get_skills_list(self):
        return [s.strip().lower() for s in self.skills.split(',') if s.strip()]
