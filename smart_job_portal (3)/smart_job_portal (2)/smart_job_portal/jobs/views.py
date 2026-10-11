from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, filters, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsEmployer, IsEmployerOrReadOnly, IsJobSeeker
from .models import JobPost, Application
from .serializers import (
    JobPostSerializer, ApplicationSerializer,
    ApplicantApplicationSerializer, ApplicationStatusSerializer,
)


class JobPostListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/jobs/          → List open jobs (public; expired/closed jobs are hidden)
    POST /api/jobs/          → Create job (employer only)
    Supports: ?search=python  ?location=hyderabad  ?job_type=remote
              ?experience_level=fresher  ?ordering=-salary_min
    """
    serializer_class   = JobPostSerializer
    permission_classes = [IsEmployerOrReadOnly]
    filter_backends    = [filters.SearchFilter, filters.OrderingFilter]
    search_fields      = ['title', 'company', 'required_skills', 'location', 'description']
    ordering_fields    = ['created_at', 'salary_min', 'salary_max', 'deadline']

    def get_queryset(self):
        qs = JobPost.objects.open().with_applicant_counts().select_related('employer')
        params    = self.request.query_params
        job_type  = params.get('job_type')
        location  = params.get('location')
        exp_level = params.get('experience_level')
        if job_type:
            qs = qs.filter(job_type=job_type)
        if location:
            qs = qs.filter(location__icontains=location)
        if exp_level:
            qs = qs.filter(experience_level=exp_level)
        return qs

    def perform_create(self, serializer):
        serializer.save(employer=self.request.user)


class JobPostDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/jobs/<id>/  → Job detail (public)
    PUT    /api/jobs/<id>/  → Update job (owner only)
    DELETE /api/jobs/<id>/  → Delete job (owner only)
    """
    queryset           = JobPost.objects.with_applicant_counts().select_related('employer')
    serializer_class   = JobPostSerializer
    permission_classes = [IsEmployerOrReadOnly]


class ApplyJobView(APIView):
    """
    POST /api/jobs/<job_id>/apply/  → Apply to a job (jobseeker only)
    """
    permission_classes = [permissions.IsAuthenticated, IsJobSeeker]

    def post(self, request, job_id):
        job = get_object_or_404(JobPost, pk=job_id)
        if not job.is_open:
            return Response({'error': 'This job is no longer accepting applications.'},
                            status=status.HTTP_400_BAD_REQUEST)

        if Application.objects.filter(job=job, applicant=request.user).exists():
            return Response({'error': 'You have already applied to this job.'},
                            status=status.HTTP_400_BAD_REQUEST)

        from matching.engine import compute_match_score
        score = compute_match_score(request.user, job)

        try:
            with transaction.atomic():
                application = Application.objects.create(
                    job=job,
                    applicant=request.user,
                    match_score=score,
                    cover_letter=request.data.get('cover_letter', '')
                )
        except IntegrityError:  # two simultaneous requests
            return Response({'error': 'You have already applied to this job.'},
                            status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'message': 'Application submitted successfully!',
            'match_score': score,
            'application': ApplicationSerializer(application).data,
        }, status=status.HTTP_201_CREATED)


class MyApplicationsView(generics.ListAPIView):
    """GET /api/jobs/my-applications/ → Jobseeker's all applications (newest first)."""
    serializer_class   = ApplicationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (Application.objects.filter(applicant=self.request.user)
                .select_related('job', 'applicant')
                .order_by('-applied_at'))


class JobApplicantsView(generics.ListAPIView):
    """
    GET /api/jobs/<job_id>/applicants/ → Employer views applicants (with resumes)
    for one of their own jobs, best match first. Optional ?status=shortlisted.
    """
    serializer_class   = ApplicantApplicationSerializer
    permission_classes = [IsEmployer]

    def get_queryset(self):
        job = get_object_or_404(JobPost, pk=self.kwargs['job_id'], employer=self.request.user)
        qs = (Application.objects.filter(job=job)
              .select_related('applicant', 'applicant__resume'))
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs


class UpdateApplicationStatusView(generics.UpdateAPIView):
    """PATCH /api/jobs/application/<id>/status/ → Employer updates application status."""
    serializer_class   = ApplicationStatusSerializer
    permission_classes = [IsEmployer]
    http_method_names  = ['patch', 'options']

    def get_queryset(self):
        return Application.objects.filter(job__employer=self.request.user)


class MyJobPostsView(generics.ListAPIView):
    """GET /api/jobs/my-posts/ → Employer sees their own job posts (open and closed)."""
    serializer_class   = JobPostSerializer
    permission_classes = [IsEmployer]

    def get_queryset(self):
        return (JobPost.objects.filter(employer=self.request.user)
                .with_applicant_counts().select_related('employer'))
