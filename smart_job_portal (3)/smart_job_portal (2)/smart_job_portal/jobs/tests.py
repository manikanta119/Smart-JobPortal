from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import UserProfile, Resume
from .models import JobPost, Application

PASSWORD = 'Sup3r-Secret-Pass!'

JOB = {
    'title': 'Backend Developer', 'company': 'Acme', 'location': 'Chennai',
    'job_type': 'full_time', 'experience_level': 'fresher',
    'description': 'Build REST APIs with Django and PostgreSQL.',
    'required_skills': 'Python, Django, REST API, PostgreSQL',
}


class JobsBase(APITestCase):
    def setUp(self):
        cache.clear()

    def make_user(self, username, role, skills=''):
        user = User.objects.create_user(username, f'{username}@example.com', PASSWORD)
        UserProfile.objects.create(user=user, role=role)
        Resume.objects.create(user=user, skills=skills)
        return user

    def as_user(self, user):
        self.client.force_authenticate(user)

    def make_job(self, employer, **overrides):
        data = {**JOB, 'employer': employer, **overrides}
        return JobPost.objects.create(**data)


class JobPostTests(JobsBase):
    def setUp(self):
        super().setUp()
        self.employer = self.make_user('boss', 'employer')
        self.seeker = self.make_user('asha', 'jobseeker', 'Python, Django')

    def test_employer_can_create_job_seeker_cannot(self):
        self.as_user(self.seeker)
        self.assertEqual(self.client.post('/api/jobs/', JOB, format='json').status_code, 403)
        self.as_user(self.employer)
        res = self.client.post('/api/jobs/', JOB, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['employer_name'], 'boss')
        self.assertEqual(res.data['total_applicants'], 0)

    def test_anonymous_can_list_but_not_create(self):
        self.make_job(self.employer)
        self.assertEqual(self.client.get('/api/jobs/').status_code, 200)
        self.assertEqual(self.client.post('/api/jobs/', JOB, format='json').status_code, 401)

    def test_expired_and_closed_jobs_hidden_from_list(self):
        self.make_job(self.employer, title='Live')
        self.make_job(self.employer, title='Expired', deadline=timezone.localdate() - timedelta(days=1))
        self.make_job(self.employer, title='Closed', status='closed')
        titles = [j['title'] for j in self.client.get('/api/jobs/').data['results']]
        self.assertEqual(titles, ['Live'])

    def test_validation_rules(self):
        self.as_user(self.employer)
        past = (timezone.localdate() - timedelta(days=2)).isoformat()
        self.assertEqual(self.client.post('/api/jobs/', {**JOB, 'deadline': past}, format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/jobs/', {**JOB, 'salary_min': 90, 'salary_max': 10}, format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/jobs/', {**JOB, 'required_skills': ' , '}, format='json').status_code, 400)

    def test_only_owner_can_edit_or_delete(self):
        job = self.make_job(self.employer)
        rival = self.make_user('rival', 'employer')
        self.as_user(rival)
        self.assertEqual(self.client.patch(f'/api/jobs/{job.id}/', {'title': 'Hacked'}, format='json').status_code, 403)
        self.assertEqual(self.client.delete(f'/api/jobs/{job.id}/').status_code, 403)
        self.as_user(self.employer)
        self.assertEqual(self.client.patch(f'/api/jobs/{job.id}/', {'title': 'Senior Dev'}, format='json').status_code, 200)

    def test_filters(self):
        self.make_job(self.employer, title='Remote Dev', job_type='remote', location='Pune')
        self.make_job(self.employer, title='Onsite Dev', location='Chennai')
        res = self.client.get('/api/jobs/?job_type=remote')
        self.assertEqual([j['title'] for j in res.data['results']], ['Remote Dev'])
        res = self.client.get('/api/jobs/?location=chen')
        self.assertEqual([j['title'] for j in res.data['results']], ['Onsite Dev'])


class ApplicationFlowTests(JobsBase):
    def setUp(self):
        super().setUp()
        self.employer = self.make_user('boss', 'employer')
        self.seeker = self.make_user('asha', 'jobseeker', 'Python, Django, REST API, PostgreSQL')
        self.job = self.make_job(self.employer)

    def apply(self, job=None, user=None, **payload):
        self.as_user(user or self.seeker)
        return self.client.post(f'/api/jobs/{(job or self.job).id}/apply/', payload, format='json')

    def test_apply_stores_match_score(self):
        res = self.apply(cover_letter='Hire me')
        self.assertEqual(res.status_code, 201)
        self.assertGreater(res.data['match_score'], 60)
        self.assertEqual(Application.objects.get().cover_letter, 'Hire me')

    def test_cannot_apply_twice(self):
        self.assertEqual(self.apply().status_code, 201)
        self.assertEqual(self.apply().status_code, 400)

    def test_employer_cannot_apply(self):
        self.assertEqual(self.apply(user=self.employer).status_code, 403)

    def test_superuser_without_profile_gets_403_not_500(self):
        admin = User.objects.create_superuser('root', 'root@example.com', PASSWORD)
        self.assertEqual(self.apply(user=admin).status_code, 403)

    def test_cannot_apply_to_expired_or_closed_job(self):
        expired = self.make_job(self.employer, deadline=timezone.localdate() - timedelta(days=1))
        closed = self.make_job(self.employer, status='closed')
        self.assertEqual(self.apply(job=expired).status_code, 400)
        self.assertEqual(self.apply(job=closed).status_code, 400)

    def test_my_applications_lists_only_own(self):
        self.apply()
        other = self.make_user('ravi', 'jobseeker', 'Java')
        self.as_user(other)
        self.assertEqual(self.client.get('/api/jobs/my-applications/').data['count'], 0)
        self.as_user(self.seeker)
        res = self.client.get('/api/jobs/my-applications/')
        self.assertEqual(res.data['count'], 1)
        self.assertEqual(res.data['results'][0]['job_id'], self.job.id)

    def test_employer_sees_applicants_with_resume_best_first(self):
        weak = self.make_user('ravi', 'jobseeker', 'Photoshop')
        self.apply()
        self.apply(user=weak)
        self.as_user(self.employer)
        res = self.client.get(f'/api/jobs/{self.job.id}/applicants/')
        self.assertEqual(res.status_code, 200)
        names = [a['applicant_name'] for a in res.data['results']]
        self.assertEqual(names, ['asha', 'ravi'])
        self.assertEqual(res.data['results'][0]['resume']['skills'], 'Python, Django, REST API, PostgreSQL')
        self.assertEqual(res.data['results'][0]['applicant_email'], 'asha@example.com')

    def test_applicants_status_filter(self):
        self.apply()
        app = Application.objects.get()
        self.as_user(self.employer)
        self.client.patch(f'/api/jobs/application/{app.id}/status/', {'status': 'shortlisted'}, format='json')
        self.assertEqual(self.client.get(f'/api/jobs/{self.job.id}/applicants/?status=shortlisted').data['count'], 1)
        self.assertEqual(self.client.get(f'/api/jobs/{self.job.id}/applicants/?status=hired').data['count'], 0)

    def test_other_employer_cannot_see_applicants_or_change_status(self):
        self.apply()
        app = Application.objects.get()
        rival = self.make_user('rival', 'employer')
        self.as_user(rival)
        self.assertEqual(self.client.get(f'/api/jobs/{self.job.id}/applicants/').status_code, 404)
        res = self.client.patch(f'/api/jobs/application/{app.id}/status/', {'status': 'hired'}, format='json')
        self.assertEqual(res.status_code, 404)

    def test_job_seeker_cannot_view_applicants_or_update_status(self):
        self.apply()
        app = Application.objects.get()
        self.as_user(self.seeker)
        self.assertEqual(self.client.get(f'/api/jobs/{self.job.id}/applicants/').status_code, 403)
        self.assertEqual(self.client.patch(f'/api/jobs/application/{app.id}/status/', {'status': 'hired'}, format='json').status_code, 403)

    def test_status_update_validates_choice_and_disallows_put(self):
        self.apply()
        app = Application.objects.get()
        self.as_user(self.employer)
        url = f'/api/jobs/application/{app.id}/status/'
        self.assertEqual(self.client.patch(url, {'status': 'banana'}, format='json').status_code, 400)
        self.assertEqual(self.client.put(url, {'status': 'hired'}, format='json').status_code, 405)

    def test_applicant_count_is_reported(self):
        self.apply()
        res = self.client.get('/api/jobs/')
        self.assertEqual(res.data['results'][0]['total_applicants'], 1)
        self.as_user(self.employer)
        self.assertEqual(self.client.get('/api/jobs/my-posts/').data['results'][0]['total_applicants'], 1)

    def test_my_posts_is_employer_only(self):
        self.as_user(self.seeker)
        self.assertEqual(self.client.get('/api/jobs/my-posts/').status_code, 403)
