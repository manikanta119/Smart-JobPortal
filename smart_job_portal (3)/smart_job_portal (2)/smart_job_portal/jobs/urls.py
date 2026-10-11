from django.urls import path
from . import views

urlpatterns = [
    # Job listings
    path('',                              views.JobPostListCreateView.as_view(),     name='job-list-create'),
    path('<int:pk>/',                     views.JobPostDetailView.as_view(),         name='job-detail'),
    # Apply
    path('<int:job_id>/apply/',           views.ApplyJobView.as_view(),              name='apply-job'),
    path('<int:job_id>/applicants/',      views.JobApplicantsView.as_view(),         name='job-applicants'),
    # My views
    path('my-applications/',             views.MyApplicationsView.as_view(),        name='my-applications'),
    path('my-posts/',                    views.MyJobPostsView.as_view(),             name='my-posts'),
    # Status update
    path('application/<int:pk>/status/', views.UpdateApplicationStatusView.as_view(), name='update-status'),
]
