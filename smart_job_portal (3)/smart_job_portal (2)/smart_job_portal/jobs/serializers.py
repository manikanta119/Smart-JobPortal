from django.utils import timezone
from rest_framework import serializers

from accounts.serializers import ResumeSerializer
from .models import JobPost, Application


class JobPostSerializer(serializers.ModelSerializer):
    employer_name    = serializers.CharField(source='employer.username', read_only=True)
    skills_list      = serializers.SerializerMethodField()
    salary_display   = serializers.CharField(source='salary_range', read_only=True)
    total_applicants = serializers.IntegerField(read_only=True)

    class Meta:
        model  = JobPost
        fields = [
            'id', 'employer_name', 'title', 'company', 'location',
            'job_type', 'experience_level', 'description', 'required_skills',
            'skills_list', 'salary_min', 'salary_max', 'salary_display',
            'deadline', 'status', 'total_applicants', 'created_at', 'updated_at'
        ]
        read_only_fields = ['employer_name', 'created_at', 'updated_at']

    def get_skills_list(self, obj):
        return obj.get_skills_list()

    def validate_required_skills(self, value):
        if not [s for s in value.split(',') if s.strip()]:
            raise serializers.ValidationError('Provide at least one required skill.')
        return value

    def validate_deadline(self, value):
        # Only block past deadlines on creation; editing an old job shouldn't fail.
        if value and self.instance is None and value < timezone.localdate():
            raise serializers.ValidationError('Deadline cannot be in the past.')
        return value

    def validate(self, attrs):
        low  = attrs.get('salary_min', getattr(self.instance, 'salary_min', None))
        high = attrs.get('salary_max', getattr(self.instance, 'salary_max', None))
        if low is not None and high is not None and low > high:
            raise serializers.ValidationError(
                {'salary_min': 'Minimum salary cannot exceed maximum salary.'}
            )
        return attrs


class ApplicationSerializer(serializers.ModelSerializer):
    """Job seeker's view of their own applications."""
    applicant_name = serializers.CharField(source='applicant.username', read_only=True)
    job_id         = serializers.IntegerField(source='job.id', read_only=True)
    job_title      = serializers.CharField(source='job.title', read_only=True)
    job_company    = serializers.CharField(source='job.company', read_only=True)

    class Meta:
        model  = Application
        fields = [
            'id', 'job_id', 'applicant_name', 'job_title', 'job_company',
            'status', 'match_score', 'cover_letter', 'applied_at', 'updated_at'
        ]
        read_only_fields = ['applicant_name', 'match_score', 'applied_at', 'updated_at']


class ApplicantApplicationSerializer(serializers.ModelSerializer):
    """Employer's view of an applicant, including their resume."""
    applicant_id    = serializers.IntegerField(source='applicant.id', read_only=True)
    applicant_name  = serializers.CharField(source='applicant.username', read_only=True)
    applicant_email = serializers.EmailField(source='applicant.email', read_only=True)
    resume          = ResumeSerializer(source='applicant.resume', read_only=True)

    class Meta:
        model  = Application
        fields = [
            'id', 'applicant_id', 'applicant_name', 'applicant_email',
            'status', 'match_score', 'cover_letter', 'applied_at', 'resume'
        ]
        read_only_fields = fields


class ApplicationStatusSerializer(serializers.ModelSerializer):
    """Used by employers to update application status."""
    class Meta:
        model  = Application
        fields = ['id', 'status']
