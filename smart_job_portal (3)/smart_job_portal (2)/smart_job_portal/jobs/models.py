from django.contrib.auth.models import User
from django.db import models
from django.db.models import Count, F, Q
from django.utils import timezone


class JobPostQuerySet(models.QuerySet):
    def open(self):
        """Jobs that are marked open and whose deadline (if any) hasn't passed."""
        today = timezone.localdate()
        return self.filter(status='open').filter(
            Q(deadline__isnull=True) | Q(deadline__gte=today)
        )

    def with_applicant_counts(self):
        """Annotate applicants_count so list views don't run a COUNT per row."""
        return self.annotate(applicants_count=Count('applications')).order_by('-created_at', 'id')


class JobPost(models.Model):
    STATUS_CHOICES = [('open', 'Open'), ('closed', 'Closed')]
    JOB_TYPE_CHOICES = [
        ('full_time', 'Full Time'),
        ('part_time', 'Part Time'),
        ('internship', 'Internship'),
        ('contract', 'Contract'),
        ('remote', 'Remote'),
    ]
    EXPERIENCE_CHOICES = [
        ('fresher', 'Fresher'),
        ('1-2', '1-2 Years'),
        ('3-5', '3-5 Years'),
        ('5+', '5+ Years'),
    ]

    employer         = models.ForeignKey(User, on_delete=models.CASCADE, related_name='job_posts')
    title            = models.CharField(max_length=200)
    company          = models.CharField(max_length=200)
    location         = models.CharField(max_length=100)
    job_type         = models.CharField(max_length=20, choices=JOB_TYPE_CHOICES, default='full_time')
    experience_level = models.CharField(max_length=20, choices=EXPERIENCE_CHOICES, default='fresher')
    description      = models.TextField()
    required_skills  = models.TextField(help_text="Comma-separated skills e.g. Python, Django, REST API")
    salary_min       = models.PositiveIntegerField(null=True, blank=True)
    salary_max       = models.PositiveIntegerField(null=True, blank=True)
    deadline         = models.DateField(null=True, blank=True)
    status           = models.CharField(max_length=10, choices=STATUS_CHOICES, default='open')
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    objects = JobPostQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at', 'id']
        constraints = [
            models.CheckConstraint(
                check=Q(salary_min__isnull=True) | Q(salary_max__isnull=True)
                      | Q(salary_min__lte=F('salary_max')),
                name='jobpost_salary_min_lte_max',
            ),
        ]

    def __str__(self):
        return f"{self.title} at {self.company}"

    def get_skills_list(self):
        return [s.strip().lower() for s in self.required_skills.split(',') if s.strip()]

    @property
    def is_open(self):
        """True if the job accepts applications right now."""
        if self.status != 'open':
            return False
        return self.deadline is None or self.deadline >= timezone.localdate()

    @property
    def salary_range(self):
        if self.salary_min and self.salary_max:
            return f"₹{self.salary_min:,} - ₹{self.salary_max:,}"
        if self.salary_min:
            return f"From ₹{self.salary_min:,}"
        if self.salary_max:
            return f"Up to ₹{self.salary_max:,}"
        return "Not disclosed"

    @property
    def total_applicants(self):
        # Uses the annotation from with_applicant_counts() when available.
        if hasattr(self, 'applicants_count'):
            return self.applicants_count
        return self.applications.count()


class Application(models.Model):
    STATUS_CHOICES = [
        ('applied', 'Applied'),
        ('shortlisted', 'Shortlisted'),
        ('interview', 'Interview Scheduled'),
        ('rejected', 'Rejected'),
        ('hired', 'Hired'),
    ]

    job         = models.ForeignKey(JobPost, on_delete=models.CASCADE, related_name='applications')
    applicant   = models.ForeignKey(User, on_delete=models.CASCADE, related_name='applications')
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default='applied')
    match_score = models.FloatField(default=0.0)
    cover_letter = models.TextField(blank=True)
    applied_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('job', 'applicant')
        ordering = ['-match_score', '-applied_at']

    def __str__(self):
        return f"{self.applicant.username} → {self.job.title} ({self.match_score}%)"
