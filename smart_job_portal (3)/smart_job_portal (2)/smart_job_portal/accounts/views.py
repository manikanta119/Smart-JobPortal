from django.contrib.auth.models import User
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .models import UserProfile, Resume
from .serializers import RegisterSerializer, UserProfileSerializer, ResumeSerializer


class RegisterView(generics.CreateAPIView):
    """Register a new user (jobseeker or employer)."""
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user  = serializer.save()
        token = RefreshToken.for_user(user)
        return Response({
            'message': 'Registration successful',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'role': user.profile.role,
            },
            'tokens': {
                'access': str(token.access_token),
                'refresh': str(token),
            }
        }, status=status.HTTP_201_CREATED)


class ProfileView(generics.RetrieveUpdateAPIView):
    """Get or update the authenticated user's profile."""
    serializer_class   = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        profile, _ = UserProfile.objects.select_related('user').get_or_create(user=self.request.user)
        return profile


class ResumeView(generics.RetrieveUpdateAPIView):
    """Get or update the authenticated user's resume.

    Updating the resume re-scores the user's active applications so employers
    always see an up-to-date match score.
    """
    serializer_class   = ResumeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        resume, _ = Resume.objects.get_or_create(
            user=self.request.user,
            defaults={'skills': ''}
        )
        return resume

    def perform_update(self, serializer):
        serializer.save()
        from matching.engine import refresh_application_scores
        refresh_application_scores(self.request.user)


class LogoutView(APIView):
    """Blacklist the supplied refresh token."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh = request.data.get('refresh')
        if not refresh:
            return Response({'error': 'The "refresh" token is required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh)
            if str(token.get('user_id')) != str(request.user.id):
                return Response({'error': 'Token does not belong to this user.'},
                                status=status.HTTP_400_BAD_REQUEST)
            token.blacklist()
        except TokenError:
            return Response({'error': 'Invalid or expired token.'},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response({'message': 'Logged out successfully'})


class UserListView(generics.ListAPIView):
    """Admin: list all user profiles."""
    queryset = UserProfile.objects.select_related('user').order_by('-created_at')
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAdminUser]
