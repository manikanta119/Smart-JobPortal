from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from .models import UserProfile, Resume

STRONG_PASSWORD = 'Sup3r-Secret-Pass!'


def register_payload(**overrides):
    payload = {
        'username': 'asha', 'email': 'asha@example.com', 'password': STRONG_PASSWORD,
        'first_name': 'Asha', 'last_name': 'K', 'role': 'jobseeker',
    }
    payload.update(overrides)
    return payload


class AuthTests(APITestCase):
    def setUp(self):
        cache.clear()  # reset throttling between tests

    def register(self, **overrides):
        return self.client.post('/api/auth/register/', register_payload(**overrides), format='json')

    def authenticate(self, access):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')

    def test_register_creates_user_profile_resume_and_tokens(self):
        res = self.register()
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertIn('access', res.data['tokens'])
        user = User.objects.get(username='asha')
        self.assertEqual(user.profile.role, 'jobseeker')
        self.assertTrue(Resume.objects.filter(user=user).exists())

    def test_weak_or_common_password_rejected(self):
        res = self.register(password='12345678')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', res.data)
        self.assertFalse(User.objects.filter(username='asha').exists())

    def test_short_password_rejected(self):
        self.assertEqual(self.register(password='aB3$').status_code, 400)

    def test_duplicate_email_rejected_case_insensitively(self):
        self.assertEqual(self.register().status_code, 201)
        res = self.register(username='other', email='ASHA@example.com')
        self.assertEqual(res.status_code, 400)
        self.assertIn('email', res.data)

    def test_invalid_role_rejected(self):
        self.assertEqual(self.register(role='admin').status_code, 400)

    def test_login_then_logout_blacklists_refresh_token(self):
        self.register()
        login = self.client.post('/api/auth/login/',
                                 {'username': 'asha', 'password': STRONG_PASSWORD}, format='json')
        self.assertEqual(login.status_code, 200)
        access, refresh = login.data['access'], login.data['refresh']

        self.authenticate(access)
        out = self.client.post('/api/auth/logout/', {'refresh': refresh}, format='json')
        self.assertEqual(out.status_code, 200)

        self.client.credentials()
        again = self.client.post('/api/auth/refresh/', {'refresh': refresh}, format='json')
        self.assertEqual(again.status_code, 401)

    def test_logout_requires_refresh_token(self):
        access = self.register().data['tokens']['access']
        self.authenticate(access)
        self.assertEqual(self.client.post('/api/auth/logout/', {}, format='json').status_code, 400)

    def test_logout_rejects_garbage_token(self):
        access = self.register().data['tokens']['access']
        self.authenticate(access)
        res = self.client.post('/api/auth/logout/', {'refresh': 'not-a-token'}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_cannot_logout_with_someone_elses_token(self):
        self.register()
        other = self.register(username='ravi', email='ravi@example.com').data['tokens']
        mine = self.client.post('/api/auth/login/',
                                {'username': 'asha', 'password': STRONG_PASSWORD}, format='json').data
        self.authenticate(mine['access'])
        res = self.client.post('/api/auth/logout/', {'refresh': other['refresh']}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_role_cannot_be_changed_through_profile_update(self):
        access = self.register().data['tokens']['access']
        self.authenticate(access)
        res = self.client.patch('/api/auth/profile/', {'role': 'employer', 'location': 'Chennai'}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(UserProfile.objects.get(user__username='asha').role, 'jobseeker')
        self.assertEqual(res.data['location'], 'Chennai')

    def test_resume_skills_are_cleaned_and_deduplicated(self):
        access = self.register().data['tokens']['access']
        self.authenticate(access)
        res = self.client.patch('/api/auth/resume/',
                                {'skills': 'Python, python , Django,,  '}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['skills'], 'Python, Django')
        self.assertEqual(res.data['skills_list'], ['python', 'django'])

    def test_resume_requires_authentication(self):
        self.assertEqual(self.client.get('/api/auth/resume/').status_code, 401)

    def test_user_list_is_admin_only(self):
        access = self.register().data['tokens']['access']
        self.authenticate(access)
        self.assertEqual(self.client.get('/api/auth/users/').status_code, 403)

        admin = User.objects.create_superuser('root', 'root@example.com', STRONG_PASSWORD)
        self.client.force_authenticate(admin)
        res = self.client.get('/api/auth/users/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['count'], 1)  # superuser has no profile row
