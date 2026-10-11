from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsEmployer
from jobs.models import JobPost
from .engine import (
    compute_match_score, get_match_details,
    get_top_matching_jobs, get_top_matching_candidates,
)


class MatchScoreView(APIView):
    """
    
    GET /api/match/<job_id>/
    Returns match score between logged-in user's resume and the job.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, job_id):
        job   = get_object_or_404(JobPost, pk=job_id)
        score = compute_match_score(request.user, job)
        return Response({
            'job_id':      job.id,
            'job_title':   job.title,
            'company':     job.company,
            'match_score': score,
            'message':     f'Your resume matches {score}% of this job requirements.'
        })


class MatchDetailsView(APIView):
    """
    GET /api/match/<job_id>/details/
    Full breakdown: matched/missing skills, matched/missing keywords, score.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, job_id):
        job     = get_object_or_404(JobPost, pk=job_id)
        details = get_match_details(request.user, job)
        return Response({
            'job_id':    job.id,
            'job_title': job.title,
            'company':   job.company,
            **details
        })


class TopJobsView(APIView):
    """
    GET /api/match/top-jobs/?limit=10
    Best-matching open jobs for the logged-in user (limit clamped to 1–50).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            limit = int(request.query_params.get('limit', 10))
        except (TypeError, ValueError):
            limit = 10
        limit = max(1, min(limit, 50))

        results = get_top_matching_jobs(request.user, limit=limit)
        data = [
            {
                'job_id':       job.id,
                'title':        job.title,
                'company':      job.company,
                'location':     job.location,
                'job_type':     job.job_type,
                'match_score':  score,
                'salary_range': job.salary_range,
            }
            for job, score in results
        ]
        return Response({'count': len(data), 'results': data})


class TopCandidatesView(APIView):
    """
    GET /api/match/<job_id>/candidates/?limit=10   (employer, own jobs only)
    Best-matching applicants for one of the employer's jobs.
    """
    permission_classes = [IsEmployer]

    def get(self, request, job_id):
        job = get_object_or_404(JobPost, pk=job_id, employer=request.user)
        try:
            limit = int(request.query_params.get('limit', 10))
        except (TypeError, ValueError):
            limit = 10
        limit = max(1, min(limit, 50))

        data = [
            {'applicant_id': user.id, 'applicant_name': user.username, 'match_score': score}
            for user, score in get_top_matching_candidates(job, limit=limit)
        ]
        return Response({'job_id': job.id, 'count': len(data), 'results': data})
