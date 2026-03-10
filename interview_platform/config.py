"""
config.py — Platform Configuration
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── OpenRouter LLM ──────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "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")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
LLM_MODEL = "arcee-ai/trinity-large-preview:free"

# ── ElevenLabs STT ──────────────────────────────────────────
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "sk_731f5124d148dce5da10b34d8789430a32317b8f5dbccdb7")

# ── Flask ────────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "interview_platform_secret_2026")
DEBUG      = os.getenv("FLASK_ENV", "development") == "development"
PORT       = int(os.getenv("PORT", 5055))

# ── Interview Settings ────────────────────────────────────────
MAX_QUESTIONS = 10
MIN_QUESTIONS = 5
INTERVIEW_DURATION_MINS = 45

DIFFICULTY_INCREASE_THRESHOLD = 75
DIFFICULTY_DECREASE_THRESHOLD = 40

# ── Interview Phases ──────────────────────────────────────────
INTERVIEW_PHASES = {
    "phase1_communication": {
        "name": "Phase 1 — Communication",
        "icon": "🗣️",
        "description": "Tests English communication, articulation, clarity of thought, and professional expression.",
        "session_type": "communication",
        "tags": ["Communication", "English", "Soft Skills"],
        "max_questions": 8,
        "color": "cyan"
    },
    "phase2_aptitude": {
        "name": "Phase 2 — Aptitude",
        "icon": "🧠",
        "description": "Pure aptitude: logical reasoning, quantitative analysis, problem-solving, and critical thinking.",
        "session_type": "aptitude",
        "tags": ["Logic", "Reasoning", "Quantitative"],
        "max_questions": 10,
        "color": "warning"
    },
    "phase3_coding": {
        "name": "Phase 3 — Coding",
        "icon": "💻",
        "description": "Advanced coding: data structures, algorithms, system design. Moderate to tough difficulty.",
        "session_type": "coding",
        "tags": ["Coding", "DS&A", "Advanced"],
        "max_questions": 10,
        "color": "primary"
    }
}

# ── Demo Users ────────────────────────────────────────────────
# 10 Candidates
DEMO_USERS = {
    "candidate1@demo.com":  {"password": "cand@123",  "role": "candidate",  "name": "Alex Johnson"},
    "candidate2@demo.com":  {"password": "cand@123",  "role": "candidate",  "name": "Priya Sharma"},
    "candidate3@demo.com":  {"password": "cand@123",  "role": "candidate",  "name": "James Wilson"},
    "candidate4@demo.com":  {"password": "cand@123",  "role": "candidate",  "name": "Ananya Reddy"},
    "candidate5@demo.com":  {"password": "cand@123",  "role": "candidate",  "name": "Michael Brown"},
    "candidate6@demo.com":  {"password": "cand@123",  "role": "candidate",  "name": "Sneha Patel"},
    "candidate7@demo.com":  {"password": "cand@123",  "role": "candidate",  "name": "David Lee"},
    "candidate8@demo.com":  {"password": "cand@123",  "role": "candidate",  "name": "Kavya Nair"},
    "candidate9@demo.com":  {"password": "cand@123",  "role": "candidate",  "name": "Robert Garcia"},
    "candidate10@demo.com": {"password": "cand@123",  "role": "candidate",  "name": "Meera Iyer"},

    # 3 Recruiters
    "recruiter1@demo.com":  {"password": "recr@123",  "role": "recruiter",  "name": "Sarah Chen"},
    "recruiter2@demo.com":  {"password": "recr@123",  "role": "recruiter",  "name": "Tom Anderson"},
    "recruiter3@demo.com":  {"password": "recr@123",  "role": "recruiter",  "name": "Neha Gupta"},
}

# ── Question Banks (fallback if LLM unavailable) ──────────────
FALLBACK_QUESTIONS = {
    "technical": [
        {"q": "Explain the difference between a stack and a queue.", "difficulty": 1, "topic": "Data Structures"},
        {"q": "Write a function to reverse a linked list.", "difficulty": 2, "topic": "Algorithms"},
        {"q": "What is the time complexity of binary search?", "difficulty": 1, "topic": "Complexity"},
        {"q": "Design a URL shortener system.", "difficulty": 3, "topic": "System Design"},
        {"q": "Explain the SOLID principles with examples.", "difficulty": 2, "topic": "OOP"},
    ],
    "behavioral": [
        {"q": "Tell me about a time you handled a conflict in a team.", "difficulty": 1, "topic": "Teamwork"},
        {"q": "Describe a project where you failed and what you learned.", "difficulty": 2, "topic": "Growth"},
        {"q": "How do you prioritize tasks when everything seems urgent?", "difficulty": 2, "topic": "Time Management"},
    ],
    "mock": [
        {"q": "Walk me through your background and what brings you here today.", "difficulty": 1, "topic": "Introduction"},
        {"q": "What are your key strengths?", "difficulty": 1, "topic": "Self-Assessment"},
    ],
    "communication": [
        {"q": "Introduce yourself in a professional manner, as if you were meeting a new team for the first time.", "difficulty": 1, "topic": "Self Introduction"},
        {"q": "Explain a complex technical concept you know to someone without a tech background.", "difficulty": 2, "topic": "Communication Clarity"},
        {"q": "Describe a situation where effective communication helped resolve a problem.", "difficulty": 2, "topic": "Professional Communication"},
    ],
    "aptitude": [
        {"q": "A train travels 120 km in 2 hours. If it increases speed by 20 km/h, how long will it take to cover 180 km?", "difficulty": 1, "topic": "Quantitative"},
        {"q": "Complete the pattern: 2, 6, 12, 20, 30, ?", "difficulty": 1, "topic": "Logical Reasoning"},
        {"q": "If all roses are flowers, and some flowers fade quickly, can we conclude that some roses fade quickly? Explain.", "difficulty": 2, "topic": "Critical Thinking"},
    ],
    "coding": [
        {"q": "Implement a function to find the longest palindromic substring in a given string. Analyze time complexity.", "difficulty": 2, "topic": "Strings & DP"},
        {"q": "Design a LRU Cache with O(1) get and put operations. Provide code.", "difficulty": 3, "topic": "Data Structures"},
        {"q": "Given a binary tree, serialize and deserialize it. Explain your approach.", "difficulty": 3, "topic": "Trees"},
    ],
}
