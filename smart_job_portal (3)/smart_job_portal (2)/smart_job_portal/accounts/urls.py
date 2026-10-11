from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from . import views

urlpatterns = [
    # Auth
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/',    TokenObtainPairView.as_view(), name='login'),
    path('refresh/',  TokenRefreshView.as_view(), name='token_refresh'),
    path('logout/',   views.LogoutView.as_view(), name='logout'),
    # Profile & Resume
    path('profile/',  views.ProfileView.as_view(), name='profile'),
    path('resume/',   views.ResumeView.as_view(), name='resume'),
    # Admin
    path('users/',    views.UserListView.as_view(), name='user-list'),
]
