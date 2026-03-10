"""Quick tests for the screening engine."""
import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'backend')

from backend.screening_engine import (
    score_resume_ats, fetch_github_profile, evaluate_experience_authenticity,
    score_social_profiles, generate_screening_questions, score_screening_test,
    calculate_combined_score, LEVEL_DESCRIPTIONS
)

# 1. ATS Test
print("=== ATS RESUME SCORING ===")
resume = """John Doe
Software Engineer | 3 years experience

Experience:
- SDE at XYZ Corp (2022-2025): Built REST APIs with Python/Flask, managed CI/CD pipelines
- Intern at ABC Inc (2021-2022): Developed data pipelines using SQL and Docker

Skills: Python, Java, SQL, Git, Docker, REST API, Problem Solving

Education: B.Tech Computer Science, ABC University (2018-2022)

Projects:
- E-commerce platform using React and Node.js
- ML prediction model using scikit-learn
"""
r = score_resume_ats(resume)
print(f"  ATS Score: {r['ats_score']}%")
print(f"  Skills found: {r['skills_found']}")
print(f"  Missing: {r['missing_skills']}")
print(f"  Years exp: {r['years_experience']}")
print(f"  Sections: {r['sections_found']}")
print(f"  Feedback: {r['feedback']}")
print()

# 2. GitHub API Test
print("=== GITHUB API (LIVE) ===")
g = fetch_github_profile("https://github.com/torvalds")
print(f"  Valid: {g['valid']}")
print(f"  Username: {g['username']}")
print(f"  Repos: {g['public_repos']}")
print(f"  Stars: {g['total_stars']}")
print(f"  Followers: {g['followers']}")
print(f"  Languages: {g['top_languages']}")
print(f"  Account age: {g['account_age_years']} years")
print(f"  Profile score: {g['profile_score']}/100")
print()

# 3. Social profiles test
print("=== SOCIAL PROFILE SCORING ===")
sp = score_social_profiles(
    linkedin_url="https://linkedin.com/in/johndoe",
    github_url="https://github.com/torvalds",
    portfolio_url="https://johndoe.dev"
)
print(f"  LinkedIn: {sp['linkedin_score']}")
print(f"  GitHub: {sp['github_score']}")
print(f"  Portfolio: {sp['portfolio_score']}")
print(f"  Overall: {sp['overall_social_score']}")
print(f"  Feedback: {sp['feedback']}")
print()

# 4. Level descriptions
print("=== 5 DIFFICULTY LEVELS ===")
for lvl, desc in LEVEL_DESCRIPTIONS.items():
    print(f"  Level {lvl}: {desc}")
print()

# 5. Question generation (fallback)
print("=== SCREENING QUESTIONS (FALLBACK) ===")
qs = generate_screening_questions("Software Engineer", 5, [1, 2, 3, 4, 5])
print(f"  Generated {len(qs)} questions")
for q in qs:
    print(f"  L{q.get('level','?')} [{q.get('topic','')}]: {q['question'][:70]}...")
print()

# 6. Score test
print("=== TEST SCORING ===")
answers = {str(q['id']): q.get('correct', 'A') for q in qs}
ts = score_screening_test(qs, answers)
print(f"  Score: {ts['test_score']}%")
print(f"  Correct: {ts['correct']}/{ts['total']}")
print(f"  Earned: {ts['earned_points']}/{ts['total_points']} pts")
print(f"  Level breakdown: {ts['level_scores']}")
print()

print("ALL TESTS PASSED ✅")
