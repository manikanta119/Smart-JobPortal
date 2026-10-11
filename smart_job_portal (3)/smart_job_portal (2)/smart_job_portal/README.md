# Smart Job Portal & Resume Matching System

A Django + PostgreSQL REST API backend for matching job seekers with employers using
skill/keyword-based resume matching.

## Tech Stack
- **Backend**: Django 4.2, Django REST Framework
- **Database**: PostgreSQL (or SQLite for quick local runs / tests)
- **Auth**: JWT (djangorestframework-simplejwt), with refresh-token blacklisting on logout
- **CORS**: django-cors-headers

## Project Structure
```
smart_job_portal/
├── manage.py
├── requirements.txt
├── .env.example           # copy to .env and fill in real values (.env is gitignored)
├── .gitignore
├── smart_job_portal/       # Core settings
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── accounts/               # User, Profile, Resume
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   ├── permissions.py
│   ├── urls.py
│   ├── admin.py
│   └── tests.py
├── jobs/                    # JobPost, Application
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   ├── urls.py
│   ├── admin.py
│   └── tests.py
└── matching/                # Matching engine
    ├── engine.py
    ├── views.py
    ├── urls.py
    └── tests.py
```

## Setup Instructions

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
```
Edit `.env`: set a real `SECRET_KEY`, and either your PostgreSQL credentials or
`USE_SQLITE=True` for a quick local/dev database.

### 3. Create PostgreSQL database (skip if using SQLite)
```sql
CREATE DATABASE jobportal_db;
```

### 4. Run migrations
```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

### 5. Run the test suite
```bash
python manage.py test
```
52 tests covering auth, jobs, applications, permissions and the matching engine.

## API Endpoints

### Auth
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/auth/register/ | Register user (validates password strength, unique email) |
| POST | /api/auth/login/ | Get JWT tokens |
| POST | /api/auth/refresh/ | Refresh access token |
| POST | /api/auth/logout/ | Blacklist refresh token |
| GET/PATCH | /api/auth/profile/ | View/update profile (role is read-only after registration) |
| GET/PATCH | /api/auth/resume/ | View/update resume (re-scores live applications on save) |
| GET | /api/auth/users/ | List all profiles (admin only) |

### Jobs
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/jobs/ | List open, non-expired jobs. Filters: `search`, `location`, `job_type`, `experience_level`, `ordering` |
| POST | /api/jobs/ | Create job (employer only) |
| GET | /api/jobs/<id>/ | Job detail |
| PUT/PATCH | /api/jobs/<id>/ | Update job (owner only) |
| DELETE | /api/jobs/<id>/ | Delete job (owner only) |
| POST | /api/jobs/<id>/apply/ | Apply to job (job seeker only, blocks duplicates/expired/closed) |
| GET | /api/jobs/<id>/applicants/ | View applicants + resumes, best match first (owner only). Filter: `status` |
| GET | /api/jobs/my-applications/ | My applications |
| GET | /api/jobs/my-posts/ | My job posts (employer only) |
| PATCH | /api/jobs/application/<id>/status/ | Update applicant status (owner only) |

### Matching
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/match/top-jobs/?limit=10 | Best-matching open jobs for the logged-in user |
| GET | /api/match/<job_id>/ | Match score for one job |
| GET | /api/match/<job_id>/details/ | Full breakdown: matched/missing skills & keywords |
| GET | /api/match/<job_id>/candidates/?limit=10 | Best-matching applicants for one of the employer's jobs |

## Matching Algorithm
`matching/engine.py` scores a resume against a job (0–100) using one function,
`analyze_match`, that both the score and details endpoints call — so they can never disagree.

- **Required skills (70% weight)**: skills are matched as phrases ("machine learning",
  "REST API" stay together, not split into separate words), checked against the resume's
  skills, experience, education and certifications. Tech-friendly tokenization keeps
  `c++`, `c#`, `node.js` intact, aliases fold `js`→`javascript`, `postgres`→`postgresql`,
  etc., and light stemming matches `developing`/`developer`/`developed`.
- **Description keywords (30% weight)**: meaningful words from the job title/description,
  with a filler list (`looking`, `candidate`, `team`, `experience`, ...) stripped out so
  generic job-ad language doesn't dilute the score.
- If a job has only skills or only a description, that side is used alone.

Resumes are re-scored automatically whenever a user updates their resume, for any
application not already `rejected` or `hired`.

## Changes from the original version
- Fixed logout (added `token_blacklist` to `INSTALLED_APPS`) and made it reject tokens
  that don't belong to the requesting user.
- Unified score computation so `/match/<id>/` and `/match/<id>/details/` always agree.
- Fixed a 500 error when a superuser (no profile) tried to apply to a job — now a clean 403.
- Fixed a crash on a non-numeric `?limit=` query param — now falls back to a default and is clamped to 1–50.
- Rewrote the matching engine: multi-word skill phrases, stemming, aliases, and filler-word
  filtering, with `required_skills` weighted above generic description text.
- Employers can now see an applicant's resume alongside their match score.
- `get_top_matching_candidates` is wired up to a real endpoint.
- Job deadlines are enforced; expired jobs no longer accept applications or appear in listings.
- Fixed N+1 queries: `get_top_matching_jobs` fetches the resume once, and job listings
  annotate applicant counts instead of running a `COUNT` per row.
- Added Django's password validators and case-insensitive unique email to registration.
- Moved secrets out of the repo (`.env` → `.env.example` + `.gitignore`), added
  `ALLOWED_HOSTS`/`CORS` allow-lists for production, shortened access-token lifetime to
  30 minutes, and added basic request throttling.
- Removed the unused Pillow dependency and a stray directory left over from a shell mistake.
- Added a 52-test suite (`accounts/tests.py`, `jobs/tests.py`, `matching/tests.py`) covering
  auth, permissions, job filtering/validation, the application flow, and the matching engine.
