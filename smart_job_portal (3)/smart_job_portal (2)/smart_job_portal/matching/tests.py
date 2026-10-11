from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.test import APITestCase

from accounts.models import UserProfile, Resume
from jobs.models import JobPost, Application
from . import engine

PASSWORD = 'Sup3r-Secret-Pass!'


def make_user(username, role='jobseeker', **resume):
    user = User.objects.create_user(username, f'{username}@example.com', PASSWORD)
    UserProfile.objects.create(user=user, role=role)
    Resume.objects.create(user=user, **resume)
    return user


def make_job(employer, **kw):
    data = dict(
        title='Backend Developer', company='Acme', location='Chennai',
        description='Build REST APIs with Django.',
        required_skills='Python, Django, REST API, PostgreSQL',
    )
    data.update(kw)
    return JobPost.objects.create(employer=employer, **data)


class EngineTests(APITestCase):
    def setUp(self):
        self.boss = make_user('boss', 'employer')

    def score(self, job, **resume):
        user = make_user(f'u{User.objects.count()}', **resume)
        return engine.compute_match_score(user, job)

    def test_perfect_and_zero_match(self):
        job = make_job(self.boss, description='')
        self.assertEqual(self.score(job, skills='Python, Django, REST API, PostgreSQL'), 70.0)  # 100% skills, title words unmatched
        self.assertEqual(self.score(job, skills='Photoshop, Illustrator'), 0.0)

    def test_score_is_partial_for_partial_skills(self):
        job = make_job(self.boss, description='')
        self.assertEqual(self.score(job, skills='Python, Django'), 35.0)  # 50% skills, title words unmatched

    def test_multiword_skills_stay_together(self):
        job = make_job(self.boss, required_skills='Machine Learning', description='', title='ML')
        self.assertEqual(self.score(job, skills='Machine Learning'), 100.0)
        # "machine" and "learning" scattered across unrelated skills must not match
        self.assertEqual(self.score(job, skills='Machine Operation', experience='Learning to cook'), 0.0)

    def test_tech_tokens_and_aliases(self):
        job = make_job(self.boss, required_skills='C++, C#, Node.js, JavaScript', description='', title='x')
        self.assertEqual(self.score(job, skills='c++, c#, nodejs, JS'), 100.0)

    def test_stemming_and_plurals(self):
        job = make_job(self.boss, required_skills='REST APIs, Databases', description='', title='x')
        self.assertEqual(self.score(job, skills='REST API, Database'), 100.0)
        job2 = make_job(self.boss, required_skills='Testing', description='', title='x')
        self.assertEqual(self.score(job2, experience='Tested and tests services'), 100.0)

    def test_skill_found_in_experience_text(self):
        job = make_job(self.boss, required_skills='Django', description='', title='x')
        self.assertEqual(self.score(job, experience='Built services using Django for 2 years'), 100.0)

    def test_generic_filler_does_not_dilute_score(self):
        filler = 'We are looking for a passionate team player with strong experience and good knowledge.'
        plain = make_job(self.boss, description='')
        noisy = make_job(self.boss, description=filler)
        skills = 'Python, Django, REST API, PostgreSQL'
        self.assertEqual(self.score(plain, skills=skills), self.score(noisy, skills=skills))

    def test_skills_outweigh_description_keywords(self):
        job = make_job(self.boss, required_skills='Python', description='Kubernetes Terraform Ansible', title='x')
        skills_only = self.score(job, skills='Python')
        keywords_only = self.score(job, skills='Kubernetes, Terraform, Ansible')
        self.assertGreater(skills_only, keywords_only)

    def test_empty_resume_and_empty_job(self):
        job = make_job(self.boss)
        self.assertEqual(self.score(job, skills=''), 0.0)
        no_user_resume = User.objects.create_user('bare', 'bare@example.com', PASSWORD)
        self.assertEqual(engine.compute_match_score(no_user_resume, job), 0.0)
        blank_job = make_job(self.boss, required_skills='', description='', title='')
        self.assertEqual(self.score(blank_job, skills='Python'), 0.0)

    def test_score_and_details_always_agree(self):
        job = make_job(self.boss, description='Own our Django REST services and PostgreSQL databases.')
        user = make_user('asha', skills='Python, Django', experience='Built APIs',
                         education='B.Tech', certifications='AWS Cloud Practitioner')
        details = engine.get_match_details(user, job)
        self.assertEqual(details['score'], engine.compute_match_score(user, job))
        self.assertIn('django', details['matched_skills'])
        self.assertIn('postgresql', details['missing_skills'])
        self.assertIn('python', [s.lower() for s in details['matched']])

    def test_certifications_count_towards_score(self):
        job = make_job(self.boss, required_skills='AWS', description='', title='x')
        self.assertEqual(self.score(job, certifications='AWS Solutions Architect'), 100.0)

    def test_top_jobs_sorted_and_skips_closed(self):
        user = make_user('asha', skills='Python, Django')
        best = make_job(self.boss, title='Best', required_skills='Python, Django', description='')
        mid = make_job(self.boss, title='Mid', required_skills='Python, Java', description='')
        make_job(self.boss, title='Closed', required_skills='Python, Django', description='', status='closed')
        ranked = engine.get_top_matching_jobs(user, limit=10)
        self.assertEqual([j.title for j, _ in ranked], ['Best', 'Mid'])

    def test_top_jobs_avoids_per_job_resume_queries(self):
        user = make_user('asha', skills='Python')
        for i in range(5):
            make_job(self.boss, title=f'Job {i}')
        with self.assertNumQueries(2):  # 1 resume + 1 jobs
            engine.get_top_matching_jobs(user)


class MatchApiTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.boss = make_user('boss', 'employer')
        self.seeker = make_user('asha', skills='Python, Django')
        self.job = make_job(self.boss, description='')

    def test_match_endpoints_require_auth(self):
        self.assertEqual(self.client.get(f'/api/match/{self.job.id}/').status_code, 401)
        self.assertEqual(self.client.get('/api/match/top-jobs/').status_code, 401)

    def test_score_and_details_endpoints_agree(self):
        self.client.force_authenticate(self.seeker)
        score = self.client.get(f'/api/match/{self.job.id}/').data['match_score']
        details = self.client.get(f'/api/match/{self.job.id}/details/').data
        self.assertEqual(score, details['score'])
        self.assertEqual(score, 35.0)  # 50% skills, title contributes unmatched keywords
        self.assertEqual(details['missing_skills'], ['rest api', 'postgresql'])

    def test_top_jobs_handles_bad_limit(self):
        self.client.force_authenticate(self.seeker)
        for bad in ('abc', '-5', '0', '9999'):
            self.assertEqual(self.client.get(f'/api/match/top-jobs/?limit={bad}').status_code, 200)
        self.assertEqual(self.client.get('/api/match/top-jobs/?limit=1').data['count'], 1)

    def test_missing_job_returns_404(self):
        self.client.force_authenticate(self.seeker)
        self.assertEqual(self.client.get('/api/match/9999/').status_code, 404)

    def test_updating_resume_refreshes_live_application_scores(self):
        self.client.force_authenticate(self.seeker)
        self.client.post(f'/api/jobs/{self.job.id}/apply/', {}, format='json')
        self.assertEqual(Application.objects.get().match_score, 35.0)

        res = self.client.patch('/api/auth/resume/',
                                {'skills': 'Python, Django, REST API, PostgreSQL'}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(Application.objects.get().match_score, 70.0)

    def test_finished_applications_keep_their_original_score(self):
        self.client.force_authenticate(self.seeker)
        self.client.post(f'/api/jobs/{self.job.id}/apply/', {}, format='json')
        Application.objects.update(status='rejected')
        self.client.patch('/api/auth/resume/', {'skills': 'Python, Django, REST API, PostgreSQL'}, format='json')
        self.assertEqual(Application.objects.get().match_score, 35.0)

    def test_top_candidates_endpoint_is_employer_only_and_sorted(self):
        strong = make_user('strong', skills='Python, Django, REST API, PostgreSQL')
        for user in (self.seeker, strong):
            self.client.force_authenticate(user)
            self.client.post(f'/api/jobs/{self.job.id}/apply/', {}, format='json')

        self.client.force_authenticate(self.seeker)
        self.assertEqual(self.client.get(f'/api/match/{self.job.id}/candidates/').status_code, 403)

        self.client.force_authenticate(self.boss)
        res = self.client.get(f'/api/match/{self.job.id}/candidates/')
        self.assertEqual([r['applicant_name'] for r in res.data['results']], ['strong', 'asha'])

        rival = make_user('rival', 'employer')
        self.client.force_authenticate(rival)
        self.assertEqual(self.client.get(f'/api/match/{self.job.id}/candidates/').status_code, 404)
