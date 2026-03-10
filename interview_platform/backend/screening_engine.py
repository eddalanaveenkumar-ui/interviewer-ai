"""
screening_engine.py — AI-Powered Candidate Screening Pipeline
Uses:
  1. GitHub API (free, public) — Real profile data
  2. LLM via OpenRouter (free model) — Resume & experience evaluation
  3. Keyword-based ATS scoring — Open-source resume matching
  4. 5-Level Difficulty Screening Tests
"""

import re
import json
import math
import requests
from collections import Counter
from config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, LLM_MODEL


# ═══════════════════════════════════════════════════════════════
# LLM HELPER
# ═══════════════════════════════════════════════════════════════

def _call_llm(messages, temperature=0.3, max_tokens=2048):
    """Send messages to OpenRouter LLM (free model: arcee-ai/trinity-large-preview)."""
    try:
        resp = requests.post(
            OPENROUTER_BASE_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": LLM_MODEL,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            },
            timeout=45
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[Screening LLM] Error: {e}")
    return ""


def _safe_json(text):
    """Extract JSON from LLM output."""
    if not text:
        return None
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        idx = text.find(start_char)
        if idx != -1:
            depth = 0
            for i in range(idx, len(text)):
                if text[i] == start_char: depth += 1
                elif text[i] == end_char: depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[idx:i+1])
                    except json.JSONDecodeError:
                        break
    try:
        return json.loads(text)
    except:
        return None


# ═══════════════════════════════════════════════════════════════
# 1. ATS RESUME SCORING (Kandidate-style open-source matching)
# ═══════════════════════════════════════════════════════════════
# Uses keyword extraction + TF matching + section detection
# Similar to open-source Resume Matcher approach

# Common tech keywords by category
SKILL_CATEGORIES = {
    "programming": ["python", "java", "javascript", "c++", "c#", "go", "rust", "ruby",
                     "php", "swift", "kotlin", "typescript", "scala", "perl", "r"],
    "web": ["html", "css", "react", "angular", "vue", "node.js", "express", "django",
            "flask", "spring", "rest api", "graphql", "next.js", "tailwind"],
    "database": ["sql", "mysql", "postgresql", "mongodb", "redis", "elasticsearch",
                  "dynamodb", "cassandra", "sqlite", "oracle", "firebase"],
    "cloud": ["aws", "azure", "gcp", "docker", "kubernetes", "terraform", "ci/cd",
              "jenkins", "github actions", "heroku", "vercel", "netlify"],
    "data_science": ["machine learning", "deep learning", "tensorflow", "pytorch",
                      "pandas", "numpy", "scikit-learn", "nlp", "computer vision", "ai"],
    "soft_skills": ["communication", "teamwork", "leadership", "problem solving",
                     "agile", "scrum", "project management", "mentoring"]
}

RESUME_SECTIONS = ["experience", "education", "skills", "projects", "certifications",
                    "achievements", "summary", "objective", "work history", "publications"]


def _extract_keywords(text):
    """Extract and count keywords from text."""
    text_lower = text.lower()
    words = re.findall(r'\b[a-z][a-z+#.]{1,25}\b', text_lower)
    return Counter(words)


def _detect_sections(text):
    """Detect resume sections present."""
    text_lower = text.lower()
    found = []
    for section in RESUME_SECTIONS:
        if section in text_lower:
            found.append(section)
    return found


def _calculate_keyword_match(resume_text, required_skills):
    """Calculate keyword match percentage."""
    text_lower = resume_text.lower()
    matched = []
    missing = []
    for skill in required_skills:
        if skill.lower() in text_lower:
            matched.append(skill)
        else:
            missing.append(skill)
    pct = int(len(matched) / max(len(required_skills), 1) * 100)
    return pct, matched, missing


def _detect_experience_years(text):
    """Extract years of experience from text."""
    patterns = [
        r'(\d+)\+?\s*years?\s*(?:of\s*)?experience',
        r'experience\s*(?:of\s*)?(\d+)\+?\s*years?',
        r'(\d{4})\s*[-–]\s*(\d{4})',
        r'(\d{4})\s*[-–]\s*(?:present|current|now)',
    ]
    years = 0
    for pattern in patterns:
        matches = re.findall(pattern, text.lower())
        if matches:
            if isinstance(matches[0], tuple):
                # Date range
                for match in matches:
                    try:
                        start = int(match[0])
                        end = int(match[1]) if match[1].isdigit() else 2026
                        years = max(years, end - start)
                    except:
                        pass
            else:
                try:
                    years = max(years, int(matches[0]))
                except:
                    pass
    return years


def score_resume_ats(resume_text, job_role="Software Engineer", required_skills=None):
    """
    ATS-style resume scoring using Kandidate-style open-source approach.
    Uses keyword matching, section detection, and format analysis.
    """
    if not resume_text or len(resume_text.strip()) < 50:
        return {
            "ats_score": 0, "keyword_match": 0, "format_score": 0,
            "experience_score": 0, "education_score": 0,
            "skills_found": [], "missing_skills": required_skills or [],
            "sections_found": [], "years_experience": 0,
            "feedback": "Resume too short or empty."
        }

    # Default skills if none specified
    if not required_skills:
        required_skills = ["Python", "Java", "SQL", "Git", "REST API",
                           "Data Structures", "Problem Solving", "Communication"]

    text_lower = resume_text.lower()
    word_count = len(resume_text.split())

    # 1. Keyword Match Score (0-100)
    keyword_pct, matched_skills, missing_skills = _calculate_keyword_match(
        resume_text, required_skills
    )

    # Bonus: check for category skills beyond required
    bonus_skills = []
    for cat, skills in SKILL_CATEGORIES.items():
        for skill in skills:
            if skill in text_lower and skill not in [s.lower() for s in matched_skills]:
                bonus_skills.append(skill)
    keyword_score = min(100, keyword_pct + len(bonus_skills) * 3)

    # 2. Format Score (0-100) — Section detection + structure
    sections = _detect_sections(resume_text)
    section_score = min(100, len(sections) * 15)

    # Check for proper formatting indicators
    format_indicators = 0
    if word_count >= 150: format_indicators += 20  # Sufficient length
    if word_count <= 1000: format_indicators += 10  # Not too long
    if re.search(r'\b[A-Z][a-z]+\s[A-Z][a-z]+\b', resume_text): format_indicators += 10  # Proper names
    if re.search(r'\d{4}', resume_text): format_indicators += 10  # Contains dates
    if re.search(r'[•\-\*]', resume_text): format_indicators += 10  # Bullet points
    if '@' in resume_text: format_indicators += 10  # Email present
    format_score = min(100, section_score + format_indicators)

    # 3. Experience Score (0-100)
    years = _detect_experience_years(resume_text)
    exp_keywords = ["developed", "built", "managed", "led", "implemented",
                     "designed", "created", "optimized", "improved", "achieved",
                     "increased", "reduced", "launched", "deployed"]
    exp_action_count = sum(1 for kw in exp_keywords if kw in text_lower)
    experience_score = min(100, years * 12 + exp_action_count * 5)

    # 4. Education Score (0-100)
    edu_keywords = ["bachelor", "master", "phd", "b.tech", "m.tech", "bsc", "msc",
                     "b.e", "m.e", "mba", "degree", "university", "college",
                     "computer science", "engineering", "certified", "certification"]
    edu_count = sum(1 for kw in edu_keywords if kw in text_lower)
    education_score = min(100, edu_count * 15)

    # Combined ATS Score (weighted)
    ats_score = int(
        keyword_score * 0.30 +
        format_score * 0.20 +
        experience_score * 0.30 +
        education_score * 0.20
    )

    feedback_parts = []
    if keyword_score >= 70: feedback_parts.append(f"Good skill match ({len(matched_skills)}/{len(required_skills)})")
    else: feedback_parts.append(f"Missing key skills: {', '.join(missing_skills[:3])}")
    if experience_score >= 60: feedback_parts.append(f"{years}+ years detected")
    if len(sections) >= 4: feedback_parts.append("Well-structured resume")
    elif len(sections) < 2: feedback_parts.append("Add more sections (experience, education, skills)")

    return {
        "ats_score": ats_score,
        "keyword_match": keyword_score,
        "format_score": format_score,
        "experience_score": experience_score,
        "education_score": education_score,
        "skills_found": matched_skills + bonus_skills[:5],
        "missing_skills": missing_skills,
        "sections_found": sections,
        "years_experience": years,
        "feedback": ". ".join(feedback_parts)
    }


# ═══════════════════════════════════════════════════════════════
# 2. GITHUB API — Real Profile Data (free, no auth, 60 req/hr)
# ═══════════════════════════════════════════════════════════════

GITHUB_API = "https://api.github.com"


def fetch_github_profile(github_url):
    """
    Fetch real data from GitHub public API.
    Returns profile stats: repos, stars, followers, languages, etc.
    No API key needed — 60 requests/hour limit.
    """
    result = {
        "valid": False, "username": "", "public_repos": 0,
        "followers": 0, "following": 0, "total_stars": 0,
        "top_languages": [], "account_age_years": 0,
        "bio": "", "profile_score": 0, "error": None
    }

    if not github_url or "github.com" not in github_url:
        result["error"] = "No GitHub URL provided"
        return result

    # Extract username
    username = github_url.rstrip("/").split("github.com/")[-1].split("/")[0].split("?")[0]
    if not username or username in ("", "orgs", "settings", "notifications"):
        result["error"] = "Invalid GitHub URL"
        return result

    result["username"] = username

    try:
        # 1. Fetch user profile
        user_resp = requests.get(f"{GITHUB_API}/users/{username}", timeout=10,
                                  headers={"Accept": "application/vnd.github.v3+json"})
        if user_resp.status_code != 200:
            result["error"] = f"GitHub API returned {user_resp.status_code}"
            return result

        user = user_resp.json()
        result["valid"] = True
        result["public_repos"] = user.get("public_repos", 0)
        result["followers"] = user.get("followers", 0)
        result["following"] = user.get("following", 0)
        result["bio"] = user.get("bio", "") or ""

        # Account age
        created = user.get("created_at", "")
        if created:
            try:
                from datetime import datetime
                created_date = datetime.fromisoformat(created.replace("Z", "+00:00"))
                age_days = (datetime.now(created_date.tzinfo) - created_date).days
                result["account_age_years"] = round(age_days / 365, 1)
            except:
                pass

        # 2. Fetch repos (top 30 by stars)
        repos_resp = requests.get(
            f"{GITHUB_API}/users/{username}/repos",
            params={"sort": "stars", "per_page": 30},
            timeout=10,
            headers={"Accept": "application/vnd.github.v3+json"}
        )
        if repos_resp.status_code == 200:
            repos = repos_resp.json()
            total_stars = sum(r.get("stargazers_count", 0) for r in repos)
            result["total_stars"] = total_stars

            # Language breakdown
            languages = Counter()
            for r in repos:
                lang = r.get("language")
                if lang:
                    languages[lang] += 1
            result["top_languages"] = [lang for lang, _ in languages.most_common(5)]

        # 3. Calculate GitHub profile score (0-100)
        score = 0
        score += min(30, result["public_repos"] * 3)       # Up to 30 for repos
        score += min(20, result["followers"] * 2)           # Up to 20 for followers
        score += min(15, result["total_stars"])              # Up to 15 for stars
        score += min(15, len(result["top_languages"]) * 5)  # Up to 15 for language diversity
        score += min(10, result["account_age_years"] * 3)   # Up to 10 for account age
        if result["bio"]: score += 10                        # 10 for having a bio
        result["profile_score"] = min(100, score)

    except requests.Timeout:
        result["error"] = "GitHub API timeout"
    except Exception as e:
        result["error"] = str(e)

    return result


# ═══════════════════════════════════════════════════════════════
# 3. EXPERIENCE AUTHENTICITY (LLM Evaluation Chain)
# ═══════════════════════════════════════════════════════════════

def evaluate_experience_authenticity(resume_text, linkedin_url="", job_role="Software Engineer"):
    """
    LangChain-style multi-step evaluation chain to detect fake/inflated experience.
    Uses the free LLM model (arcee-ai/trinity-large-preview:free via OpenRouter).
    """
    if not resume_text or len(resume_text.strip()) < 50:
        return {
            "authenticity_score": 0, "confidence": 0,
            "verdict": "insufficient_data",
            "red_flags": ["Resume too short to evaluate"],
            "positive_signals": [],
            "chain_reasoning": "Not enough data for evaluation chain."
        }

    prompt = f"""You are a senior HR fraud detection specialist. Evaluate this resume authenticity.

EVALUATION CHAIN:
Step 1 — CLAIM EXTRACTION: Extract job titles, companies, durations, achievements
Step 2 — CONSISTENCY CHECK: Do dates/progression/responsibilities make sense?
Step 3 — RED FLAG DETECTION: Vague duties, title inflation, impossible claims, buzzword stuffing
Step 4 — POSITIVE SIGNALS: Specific projects, measurable outcomes, realistic progression

RESUME:
\"\"\"{resume_text[:3000]}\"\"\"

LinkedIn: {linkedin_url or "N/A"}
Role: {job_role}

Return ONLY JSON:
{{
    "authenticity_score": 75,
    "confidence": 80,
    "verdict": "likely_authentic|possibly_inflated|likely_fake|insufficient_data",
    "red_flags": ["flag 1"],
    "positive_signals": ["signal 1"],
    "chain_reasoning": "Step-by-step explanation",
    "risk_level": "low|medium|high"
}}"""

    messages = [
        {"role": "system", "content": "You are a HR fraud detection AI. Return ONLY valid JSON."},
        {"role": "user", "content": prompt}
    ]

    result = _call_llm(messages, temperature=0.2)
    parsed = _safe_json(result)

    if not parsed:
        # Fallback: heuristic scoring
        text_lower = resume_text.lower()
        score = 50
        red_flags = []
        pos_signals = []

        # Check for specifics (good sign)
        if re.search(r'\d+%', resume_text): score += 10; pos_signals.append("Contains measurable metrics")
        if re.search(r'\d{4}', resume_text): score += 5; pos_signals.append("Contains specific dates")
        if len(resume_text.split()) > 200: score += 5; pos_signals.append("Detailed content")

        # Check for red flags
        buzzwords = ["synergy", "leverage", "paradigm", "holistic", "disrupt"]
        bw_count = sum(1 for bw in buzzwords if bw in text_lower)
        if bw_count >= 3: score -= 15; red_flags.append("Excessive buzzwords")
        if "senior" in text_lower and "0 year" in text_lower:
            score -= 20; red_flags.append("Senior title with no experience")

        return {
            "authenticity_score": max(10, min(100, score)),
            "confidence": 40,
            "verdict": "likely_authentic" if score >= 60 else "possibly_inflated",
            "red_flags": red_flags or ["Could not complete full AI evaluation"],
            "positive_signals": pos_signals,
            "chain_reasoning": "Heuristic fallback: LLM unavailable."
        }

    return parsed


# ═══════════════════════════════════════════════════════════════
# 4. SOCIAL PROFILE ASSESSMENT (GitHub API + URL validation)
# ═══════════════════════════════════════════════════════════════

def score_social_profiles(linkedin_url="", github_url="", portfolio_url="", resume_text=""):
    """
    Score candidate's social/professional presence.
    Uses REAL GitHub API data + LinkedIn URL validation.
    """
    score_parts = {
        "linkedin_score": 0,
        "github_score": 0,
        "github_data": None,
        "portfolio_score": 0,
        "profile_completeness": 0,
        "overall_social_score": 0,
        "feedback": ""
    }

    provided = 0

    # ── LinkedIn scoring (URL validation) ──
    if linkedin_url and linkedin_url.strip():
        linkedin_url = linkedin_url.strip()
        if "linkedin.com/in/" in linkedin_url:
            score_parts["linkedin_score"] = 70
            profile_slug = linkedin_url.split("/in/")[-1].strip("/")
            if profile_slug and not re.match(r'^[a-z0-9\-]{30,}$', profile_slug):
                score_parts["linkedin_score"] = 85  # Custom URL = more professional
            provided += 1
        elif "linkedin.com" in linkedin_url:
            score_parts["linkedin_score"] = 40
            provided += 1

    # ── GitHub scoring (REAL API DATA) ──
    if github_url and github_url.strip():
        github_data = fetch_github_profile(github_url)
        score_parts["github_data"] = github_data

        if github_data["valid"]:
            score_parts["github_score"] = github_data["profile_score"]
            provided += 1
        elif "github.com" in github_url:
            score_parts["github_score"] = 30  # URL exists but API failed
            provided += 1

    # ── Portfolio scoring ──
    if portfolio_url and portfolio_url.strip():
        score_parts["portfolio_score"] = 70
        provided += 1

    # ── Completeness ──
    score_parts["profile_completeness"] = int(provided / 3 * 100)

    # ── Overall weighted score ──
    weights = [
        (score_parts["linkedin_score"], 0.35),
        (score_parts["github_score"], 0.40),
        (score_parts["portfolio_score"], 0.25)
    ]
    weighted_sum = sum(s * w for s, w in weights if s > 0)
    weight_total = sum(w for s, w in weights if s > 0)
    score_parts["overall_social_score"] = int(weighted_sum / weight_total) if weight_total > 0 else 0

    # ── Feedback ──
    feedback = []
    if not linkedin_url: feedback.append("No LinkedIn")
    if not github_url: feedback.append("No GitHub")
    elif score_parts.get("github_data", {}).get("valid"):
        gd = score_parts["github_data"]
        feedback.append(f"GitHub: {gd['public_repos']} repos, {gd['followers']} followers, {gd['total_stars']}⭐")
    if provided == 0: feedback.append("No profiles — low visibility")
    elif provided == 3: feedback.append("All profiles provided ✓")
    score_parts["feedback"] = " · ".join(feedback)

    return score_parts


# ═══════════════════════════════════════════════════════════════
# 5. SCREENING TEST — 5 DIFFICULTY LEVELS
# ═══════════════════════════════════════════════════════════════

# Level descriptions for prompt
LEVEL_DESCRIPTIONS = {
    1: "EASY — Basic concepts, definitions, simple recall. A fresher should answer easily.",
    2: "MODERATE — Requires understanding, simple application of concepts.",
    3: "INTERMEDIATE — Multi-step reasoning, moderate problem solving, real scenarios.",
    4: "HARD — Complex analysis, advanced concepts, tricky edge cases.",
    5: "VERY HARD — Expert-level, advanced algorithms, system design, brain-teasers. Only top candidates pass."
}

# Fallback questions by level
FALLBACK_QUESTIONS_BY_LEVEL = {
    1: [
        {"id": 1, "question": "What does HTML stand for?",
         "type": "mcq", "options": ["A) Hyper Text Markup Language", "B) High Tech Modern Language",
                                     "C) Hyper Transfer Markup Language", "D) Home Tool Markup Language"],
         "correct": "A", "topic": "Web Basics", "points": 10, "level": 1},
        {"id": 2, "question": "Which data structure uses FIFO?",
         "type": "mcq", "options": ["A) Stack", "B) Queue", "C) Tree", "D) Graph"],
         "correct": "B", "topic": "Data Structures", "points": 10, "level": 1},
    ],
    2: [
        {"id": 1, "question": "What is the time complexity of binary search?",
         "type": "mcq", "options": ["A) O(n)", "B) O(log n)", "C) O(n²)", "D) O(1)"],
         "correct": "B", "topic": "Algorithms", "points": 15, "level": 2},
        {"id": 2, "question": "In SQL, which clause is used to filter grouped results?",
         "type": "mcq", "options": ["A) WHERE", "B) FILTER", "C) HAVING", "D) GROUP BY"],
         "correct": "C", "topic": "Databases", "points": 15, "level": 2},
    ],
    3: [
        {"id": 1, "question": "What is the output of: [1,2,3].map(x => x*2).filter(x => x>3)?",
         "type": "mcq", "options": ["A) [4, 6]", "B) [2, 4, 6]", "C) [6]", "D) [4]"],
         "correct": "A", "topic": "JavaScript", "points": 20, "level": 3},
        {"id": 2, "question": "If a project deadline is moved up by 2 weeks with no scope change, what is the BEST approach?",
         "type": "mcq", "options": ["A) Work overtime", "B) Assess scope, prioritize, communicate risks",
                                     "C) Ask for more team members", "D) Reduce testing"],
         "correct": "B", "topic": "Situational", "points": 20, "level": 3},
    ],
    4: [
        {"id": 1, "question": "What is the space complexity of merge sort?",
         "type": "mcq", "options": ["A) O(1)", "B) O(log n)", "C) O(n)", "D) O(n log n)"],
         "correct": "C", "topic": "Algorithms", "points": 25, "level": 4},
        {"id": 2, "question": "In a microservices architecture, what pattern prevents cascading failures?",
         "type": "mcq", "options": ["A) Singleton", "B) Circuit Breaker", "C) Observer", "D) Factory"],
         "correct": "B", "topic": "System Design", "points": 25, "level": 4},
    ],
    5: [
        {"id": 1, "question": "Given n integers, find the length of the longest increasing subsequence. What is the optimal time complexity?",
         "type": "mcq", "options": ["A) O(n²)", "B) O(n log n)", "C) O(2^n)", "D) O(n)"],
         "correct": "B", "topic": "Advanced Algorithms", "points": 30, "level": 5},
        {"id": 2, "question": "In CAP theorem, a distributed system can guarantee at most how many of Consistency, Availability, Partition tolerance?",
         "type": "mcq", "options": ["A) All 3", "B) 2 out of 3", "C) 1 out of 3", "D) Depends on implementation"],
         "correct": "B", "topic": "Distributed Systems", "points": 30, "level": 5},
    ]
}


def generate_screening_questions(job_role="Software Engineer", num_questions=5, levels=None):
    """
    Generate screening test questions across 5 difficulty levels.
    levels: list of levels to include, e.g. [1,2,3] or [3,4,5]
    If None, uses progressive difficulty: level 1→5 across the questions.
    """
    if levels is None:
        # Default: progressive difficulty across questions
        levels = []
        for i in range(num_questions):
            level = min(5, max(1, int(i / num_questions * 5) + 1))
            levels.append(level)

    level_desc_block = "\n".join(
        f"Level {l}: {LEVEL_DESCRIPTIONS[l]}" for l in sorted(set(levels))
    )

    prompt = f"""Generate {num_questions} screening questions for a {job_role} position.
Each question must have an assigned difficulty level.

DIFFICULTY LEVELS:
{level_desc_block}

REQUIRED LEVEL DISTRIBUTION: {levels}

For each question, use this format in a JSON array:
{{
    "questions": [
        {{
            "id": 1,
            "question": "Question text",
            "type": "mcq",
            "options": ["A) Option 1", "B) Option 2", "C) Option 3", "D) Option 4"],
            "correct": "B",
            "topic": "Topic Name",
            "points": 20,
            "level": 3
        }}
    ]
}}

Points per level: Level 1=10, Level 2=15, Level 3=20, Level 4=25, Level 5=30

Mix topics: aptitude, logical reasoning, domain knowledge, situational judgment.
Level 5 should be VERY HARD — only experts can answer.
Return ONLY valid JSON."""

    messages = [
        {"role": "system", "content": "You generate test questions. Return ONLY valid JSON."},
        {"role": "user", "content": prompt}
    ]

    result = _call_llm(messages, temperature=0.5)
    parsed = _safe_json(result)

    if parsed and "questions" in parsed:
        return parsed["questions"]

    # Fallback: build from pre-made questions
    questions = []
    for i, level in enumerate(levels):
        level_qs = FALLBACK_QUESTIONS_BY_LEVEL.get(level, FALLBACK_QUESTIONS_BY_LEVEL[1])
        q = level_qs[i % len(level_qs)].copy()
        q["id"] = i + 1
        questions.append(q)

    return questions


def score_screening_test(questions, answers):
    """Score the screening test answers. Returns 0-100 with per-level breakdown."""
    if not questions or not answers:
        return {"test_score": 0, "correct": 0, "total": 0, "details": [], "level_scores": {}}

    correct_count = 0
    total_points = 0
    earned_points = 0
    details = []
    level_scores = {}

    for q in questions:
        qid = str(q.get("id", ""))
        answer = answers.get(qid, "").strip().upper()
        correct_answer = q.get("correct", "").strip().upper()
        points = q.get("points", 20)
        level = q.get("level", 1)
        total_points += points

        is_correct = False
        if q.get("type") == "mcq":
            answer_letter = answer[0] if answer else ""
            correct_letter = correct_answer[0] if correct_answer else ""
            is_correct = answer_letter == correct_letter
        else:
            keywords = q.get("correct_keywords", [])
            answer_lower = answer.lower()
            is_correct = any(kw.lower() in answer_lower for kw in keywords) if keywords else False

        if is_correct:
            correct_count += 1
            earned_points += points

        details.append({
            "question_id": qid, "level": level,
            "correct": is_correct, "your_answer": answer,
            "correct_answer": correct_answer, "points": points
        })

        # Per-level tracking
        if level not in level_scores:
            level_scores[level] = {"correct": 0, "total": 0, "points_earned": 0, "points_possible": 0}
        level_scores[level]["total"] += 1
        level_scores[level]["points_possible"] += points
        if is_correct:
            level_scores[level]["correct"] += 1
            level_scores[level]["points_earned"] += points

    return {
        "test_score": int(earned_points / max(total_points, 1) * 100),
        "correct": correct_count,
        "total": len(questions),
        "earned_points": earned_points,
        "total_points": total_points,
        "details": details,
        "level_scores": level_scores
    }


# ═══════════════════════════════════════════════════════════════
# 6. COMBINED SCREENING PIPELINE
# ═══════════════════════════════════════════════════════════════

SCREENING_WEIGHTS = {
    "ats_resume": 0.25,
    "experience_auth": 0.20,
    "social_profiles": 0.15,
    "screening_test": 0.40
}

SCREENING_PASS_THRESHOLD = 55


def calculate_combined_score(ats_result, auth_result, social_result, test_result):
    """Calculate weighted combined screening score."""
    ats_score = ats_result.get("ats_score", 0)
    auth_score = auth_result.get("authenticity_score", 50)
    social_score = social_result.get("overall_social_score", 0)
    test_score = test_result.get("test_score", 0)

    combined = int(
        ats_score * SCREENING_WEIGHTS["ats_resume"] +
        auth_score * SCREENING_WEIGHTS["experience_auth"] +
        social_score * SCREENING_WEIGHTS["social_profiles"] +
        test_score * SCREENING_WEIGHTS["screening_test"]
    )

    passed = combined >= SCREENING_PASS_THRESHOLD

    return {
        "combined_score": combined,
        "passed": passed,
        "threshold": SCREENING_PASS_THRESHOLD,
        "breakdown": {
            "ats_resume": {"score": ats_score, "weight": "25%"},
            "experience_authenticity": {"score": auth_score, "weight": "20%"},
            "social_profiles": {"score": social_score, "weight": "15%"},
            "screening_test": {"score": test_score, "weight": "40%"}
        },
        "verdict": "APPROVED for AI Interview" if passed else "BELOW THRESHOLD — Not selected"
    }
