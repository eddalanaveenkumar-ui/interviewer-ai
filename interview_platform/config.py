"""
config.py — Platform Configuration
Set your OpenRouter API key here or in a .env file.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── OpenRouter LLM ──────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "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")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
LLM_MODEL = "arcee-ai/trinity-large-preview:free"

# ── Flask ────────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "interview_platform_secret_2026")
DEBUG = True
PORT = 5055

# ── Interview Settings ────────────────────────────────────────
MAX_QUESTIONS = 10          # max questions per session
MIN_QUESTIONS = 5           # minimum before ending
INTERVIEW_DURATION_MINS = 45

# Difficulty scoring thresholds
DIFFICULTY_INCREASE_THRESHOLD = 75   # score > this → harder question
DIFFICULTY_DECREASE_THRESHOLD = 40   # score < this → easier question

# ── Demo Users (replace with real DB in production) ──────────
DEMO_USERS = {
    "candidate@demo.com": {"password": "demo123", "role": "candidate", "name": "Alex Johnson"},
    "recruiter@demo.com": {"password": "recruiter123", "role": "recruiter", "name": "Sarah Chen"},
    "admin@demo.com":     {"password": "admin123",     "role": "admin",     "name": "Admin User"},
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
        {"q": "Tell me about your greatest professional achievement.", "difficulty": 1, "topic": "Accomplishment"},
        {"q": "How do you handle feedback or criticism?", "difficulty": 1, "topic": "Communication"},
    ],
    "mock": [
        {"q": "Walk me through your background and what brings you here today.", "difficulty": 1, "topic": "Introduction"},
        {"q": "What are your key strengths?", "difficulty": 1, "topic": "Self-Assessment"},
        {"q": "Where do you see yourself in 5 years?", "difficulty": 1, "topic": "Goals"},
    ]
}
