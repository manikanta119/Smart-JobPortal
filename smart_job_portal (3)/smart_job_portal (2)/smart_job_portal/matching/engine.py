"""
Resume Matching Engine
======================
Keyword/skill matching between a user's resume and a job posting.

How the score is computed (0.0 – 100.0)
---------------------------------------
1. **Required skills (70%)** – the job's comma-separated ``required_skills`` are
   treated as *phrases* ("machine learning", "REST API" stay together). A skill
   is matched if the phrase appears in the resume (skills, experience, education
   or certifications), or if all of its words appear in the resume's skills list.
2. **Description keywords (30%)** – meaningful words from the job title and
   description (generic job-ad filler removed) that also appear in the resume.

If a job lists no skills, the keyword score is used alone (and vice-versa).

Both sides are normalised the same way: lowercase, tech-friendly tokenisation
(``c++``, ``c#``, ``node.js`` survive), a few aliases (``js`` → ``javascript``)
and light stemming (``developing`` / ``developer`` / ``developed`` all match).

Every public function goes through ``analyze_match`` so the score shown by
``/api/match/<id>/`` and ``/api/match/<id>/details/`` can never disagree.
"""
import re

SKILL_WEIGHT = 0.7
KEYWORD_WEIGHT = 0.3

STOPWORDS = {
    'and', 'or', 'the', 'a', 'an', 'in', 'with', 'for', 'of',
    'to', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
    'can', 'could', 'should', 'may', 'might', 'shall', 'must',
    'that', 'this', 'these', 'those', 'it', 'its', 'at', 'by',
    'from', 'as', 'into', 'through', 'during', 'before', 'after',
    'above', 'below', 'up', 'down', 'out', 'on', 'off', 'over',
    'under', 'between', 'each', 'more', 'most', 'other', 'some',
    'such', 'no', 'not', 'only', 'same', 'so', 'than', 'too',
    'very', 'just', 'because', 'while', 'although', 'however',
}

# Words that appear in nearly every job ad and say nothing about fit.
JOB_AD_FILLER = {
    'looking', 'candidate', 'candidates', 'team', 'teams', 'work', 'working',
    'experience', 'experienced', 'years', 'year', 'required', 'requirements',
    'requirement', 'responsibilities', 'responsibility', 'ability', 'able',
    'strong', 'good', 'great', 'excellent', 'knowledge', 'skills', 'skill',
    'role', 'job', 'company', 'join', 'preferred', 'plus', 'etc', 'using',
    'use', 'used', 'well', 'new', 'need', 'needed', 'help', 'ideal', 'understanding',
    'including', 'include', 'seeking', 'opportunity', 'position', 'hiring',
    'you', 'your', 'our', 'we', 'they', 'their', 'who', 'what', 'all', 'any',
    'both', 'also', 'across', 'within', 'about', 'like', 'such', 'based',
    'day', 'high', 'quality', 'environment', 'fast', 'paced', 'passionate',
}

ALIASES = {
    'js': 'javascript', 'ts': 'typescript', 'py': 'python', 'golang': 'go',
    'node': 'nodejs', 'node.js': 'nodejs', 'reactjs': 'react', 'react.js': 'react',
    'vuejs': 'vue', 'vue.js': 'vue', 'next.js': 'nextjs', 'expressjs': 'express',
    'express.js': 'express', 'postgres': 'postgresql', 'k8s': 'kubernetes',
    'restful': 'rest', 'mongo': 'mongodb',
}

_TOKEN_RE = re.compile(r'[a-z0-9+#.]+')
_SKILL_SPLIT_RE = re.compile(r'[,;\n|/]+')
_SUFFIXES = (('ies', 'y'), ('ing', ''), ('ment', ''), ('ers', ''),
             ('er', ''), ('ed', ''), ('s', ''))


# --------------------------------------------------------------------------- #
# Text normalisation
# --------------------------------------------------------------------------- #
def _stem(token: str) -> str:
    token = ALIASES.get(token, token)
    if len(token) <= 3 or not token.isalpha():
        return token
    for suffix, repl in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            if suffix == 's' and token.endswith('ss'):
                continue
            token = token[:-len(suffix)] + repl
            break
    if len(token) > 3 and token.endswith('e'):
        token = token[:-1]
    return token


def _raw_tokens(text: str) -> list:
    """Lowercase tokens; keeps c++, c#, node.js; strips stray dots."""
    if not text:
        return []
    return [t for t in (tok.strip('.') for tok in _TOKEN_RE.findall(text.lower())) if t]


def _stem_stream(text: str) -> list:
    """Ordered stemmed tokens with stopwords removed (used for phrase search)."""
    return [_stem(t) for t in _raw_tokens(text) if t not in STOPWORDS]


def _keyword_map(text: str) -> dict:
    """{stem: first original word} for meaningful (non-filler) words."""
    result = {}
    for tok in _raw_tokens(text):
        if len(tok) <= 2 or tok in STOPWORDS or tok in JOB_AD_FILLER:
            continue
        result.setdefault(_stem(tok), tok)
    return result


def extract_keywords(text: str) -> set:
    """Set of normalised (stemmed) keywords found in ``text``."""
    return set(_keyword_map(text))


def _parse_skills(text: str) -> list:
    """'Python, Machine Learning' -> [('python', ('python',)), ('machine learning', (...))]"""
    skills, seen = [], set()
    for piece in _SKILL_SPLIT_RE.split(text or ''):
        raw = [t for t in _raw_tokens(piece)]
        tokens = [t for t in raw if t not in STOPWORDS] or raw
        stems = tuple(_stem(t) for t in tokens)
        if stems and stems not in seen:
            seen.add(stems)
            skills.append((' '.join(tokens), stems))
    return skills


def _contains_phrase(stream: list, stream_set: set, phrase: tuple) -> bool:
    n = len(phrase)
    if n == 0:
        return False
    if n == 1:
        return phrase[0] in stream_set
    return any(tuple(stream[i:i + n]) == phrase for i in range(len(stream) - n + 1))


# --------------------------------------------------------------------------- #
# Core analysis (single source of truth)
# --------------------------------------------------------------------------- #
def _get_resume(user):
    from accounts.models import Resume
    return Resume.objects.filter(user=user).first()


def _empty_result():
    return {
        'score': 0.0, 'skills_score': 0.0, 'keyword_score': 0.0,
        'matched_skills': [], 'missing_skills': [], 'extra_skills': [],
        'matched_keywords': [], 'missing_keywords': [],
        'total_job_skills': 0, 'total_job_keywords': 0,
    }


def analyze_match(resume, job) -> dict:
    """Full match breakdown between a Resume (or None) and a JobPost."""
    result = _empty_result()
    if resume is None:
        return result

    resume_text = ' '.join([
        resume.skills, resume.experience, resume.education, resume.certifications,
    ])
    stream = _stem_stream(resume_text)
    stream_set = set(stream)
    resume_skill_stems = {t for _, stems in _parse_skills(resume.skills) for t in stems}

    # --- Required skills (phrase matching) ---------------------------------
    job_skills = _parse_skills(job.required_skills)
    matched_skills, missing_skills = [], []
    for display, stems in job_skills:
        found = _contains_phrase(stream, stream_set, stems) or (
            len(stems) > 1 and all(s in resume_skill_stems for s in stems)
        )
        (matched_skills if found else missing_skills).append(display)

    job_skill_stems = {stems for _, stems in job_skills}
    extra_skills = [d for d, stems in _parse_skills(resume.skills) if stems not in job_skill_stems]

    # --- Description keywords (skills already counted above are excluded) ---
    skill_tokens = {t for _, stems in job_skills for t in stems}
    job_kw = {
        stem: word
        for stem, word in _keyword_map(f'{job.title} {job.description}').items()
        if stem not in skill_tokens
    }
    matched_kw = sorted(word for stem, word in job_kw.items() if stem in stream_set)
    missing_kw = sorted(word for stem, word in job_kw.items() if stem not in stream_set)

    # --- Scores -------------------------------------------------------------
    skills_score = (len(matched_skills) / len(job_skills) * 100) if job_skills else 0.0
    keyword_score = (len(matched_kw) / len(job_kw) * 100) if job_kw else 0.0

    if job_skills and job_kw:
        score = SKILL_WEIGHT * skills_score + KEYWORD_WEIGHT * keyword_score
    elif job_skills:
        score = skills_score
    else:
        score = keyword_score

    result.update({
        'score': round(min(score, 100.0), 2),
        'skills_score': round(skills_score, 2),
        'keyword_score': round(keyword_score, 2),
        'matched_skills': matched_skills,
        'missing_skills': missing_skills,
        'extra_skills': extra_skills,
        'matched_keywords': matched_kw,
        'missing_keywords': missing_kw,
        'total_job_skills': len(job_skills),
        'total_job_keywords': len(job_kw),
    })
    return result


# --------------------------------------------------------------------------- #
# Public API used by the views
# --------------------------------------------------------------------------- #
def compute_match_score(user, job) -> float:
    """Match percentage (0.0 – 100.0) between the user's resume and a job."""
    return analyze_match(_get_resume(user), job)['score']


def get_match_details(user, job) -> dict:
    """Detailed breakdown; ``score`` is guaranteed equal to compute_match_score()."""
    details = analyze_match(_get_resume(user), job)
    details['matched'] = details['matched_skills'] + details['matched_keywords']
    details['missing'] = details['missing_skills'] + details['missing_keywords']
    details['matched_count'] = len(details['matched'])
    details['total_job_keywords_and_skills'] = (
        details['total_job_skills'] + details['total_job_keywords']
    )
    return details


def get_top_matching_jobs(user, limit: int = 10) -> list:
    """(job, score) tuples for currently open jobs, best match first."""
    from jobs.models import JobPost
    resume = _get_resume(user)  # fetched once, not once per job
    scored = [(job, analyze_match(resume, job)['score']) for job in JobPost.objects.open()]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:limit]


def get_top_matching_candidates(job, limit: int = 10) -> list:
    """(user, score) for applicants of a job (stored scores), best first."""
    applications = job.applications.select_related('applicant')
    scored = [(app.applicant, app.match_score) for app in applications]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:limit]


def refresh_application_scores(user) -> int:
    """Re-score a user's live applications after their resume changed."""
    from jobs.models import Application
    resume = _get_resume(user)
    applications = list(
        Application.objects.filter(applicant=user, job__status='open')
        .exclude(status__in=['rejected', 'hired'])
        .select_related('job')
    )
    for application in applications:
        application.match_score = analyze_match(resume, application.job)['score']
    if applications:
        Application.objects.bulk_update(applications, ['match_score'])
    return len(applications)
