from django.urls import path
from . import views

urlpatterns = [
    path('top-jobs/',               views.TopJobsView.as_view(),       name='top-matching-jobs'),
    path('<int:job_id>/',           views.MatchScoreView.as_view(),    name='match-score'),
    path('<int:job_id>/details/',   views.MatchDetailsView.as_view(),  name='match-details'),
    path('<int:job_id>/candidates/', views.TopCandidatesView.as_view(), name='top-candidates'),
]
