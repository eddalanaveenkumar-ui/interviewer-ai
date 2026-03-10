"""
app.py — Main Flask Application
AI-Driven Interview Platform with Recruitment Pipeline
"""

import os, sys, json, uuid
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from werkzeug.utils import secure_filename

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from config import SECRET_KEY, DEBUG, PORT, DEMO_USERS, MAX_QUESTIONS, MIN_QUESTIONS, INTERVIEW_PHASES
from backend.ai_engine import (
    generate_opening_question,
    evaluate_and_adapt,
    generate_final_report
)
from backend.screening_engine import (
    score_resume_ats,
    evaluate_experience_authenticity,
    score_social_profiles,
    generate_screening_questions,
    score_screening_test,
    calculate_combined_score
)

app = Flask(__name__)
app.secret_key = SECRET_KEY
CORS(app)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB max upload

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
UPLOADS_DIR = DATA_DIR / "resumes"
UPLOADS_DIR.mkdir(exist_ok=True)

# ── In-Memory Stores ────────────────────────────────────────
interview_sessions = {}   # session_id → session data
job_postings = {}         # job_id → job posting data
applications = {}         # application_id → application data


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def save_session_to_disk(session_id: str):
    path = DATA_DIR / f"{session_id}.json"
    with open(path, "w") as f:
        json.dump(interview_sessions.get(session_id, {}), f, indent=2, default=str)


def load_session_from_disk(session_id: str) -> dict:
    path = DATA_DIR / f"{session_id}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def get_all_sessions_for_user(email: str) -> list:
    sessions = []
    for p in DATA_DIR.glob("*.json"):
        try:
            with open(p) as f:
                d = json.load(f)
            # Skip malformed records
            if not isinstance(d, dict):
                continue
            if d.get("candidate_email") == email:
                sessions.append(d)
        except Exception:
            pass
    return sorted(sessions, key=lambda x: x.get("started_at", ""), reverse=True)


def get_all_sessions() -> list:
    sessions = []
    for p in DATA_DIR.glob("*.json"):
        try:
            with open(p) as f:
                d = json.load(f)
            if not isinstance(d, dict):
                continue
            sessions.append(d)
        except Exception:
            pass
    return sorted(sessions, key=lambda x: x.get("started_at", ""), reverse=True)


# ═══════════════════════════════════════════════════════════════
# AUTH ROUTES
# ═══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    if "user" in session:
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/login", methods=["GET"])
def login_page():
    if "user" in session:
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.get_json()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    user = DEMO_USERS.get(email)
    if not user or user["password"] != password:
        return jsonify({"success": False, "error": "Invalid email or password"}), 401

    session["user"] = {
        "email": email,
        "name": user["name"],
        "role": user["role"]
    }
    return jsonify({"success": True, "role": user["role"], "name": user["name"]})


@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"success": True})


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ═══════════════════════════════════════════════════════════════
# DASHBOARD — Role-based
# ═══════════════════════════════════════════════════════════════

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login_page"))
    user = session["user"]
    if user["role"] == "recruiter":
        return redirect(url_for("recruiter_dashboard"))
    # Candidate
    past = get_all_sessions_for_user(user["email"])
    return render_template("dashboard.html", user=user, past_sessions=past[:10], phases=INTERVIEW_PHASES)


@app.route("/api/dashboard/stats")
def dashboard_stats():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    user = session["user"]
    past = get_all_sessions_for_user(user["email"])
    completed = [s for s in past if s.get("status") == "completed"]
    avg_score = 0
    if completed:
        scores = [(s.get("report") or {}).get("overall_score", 0) for s in completed]
        avg_score = int(sum(scores) / len(scores)) if scores else 0

    return jsonify({
        "total_sessions": len(past),
        "completed": len(completed),
        "avg_score": avg_score,
        "recent": past[:3]
    })


# ═══════════════════════════════════════════════════════════════
# RECRUITER DASHBOARD
# ═══════════════════════════════════════════════════════════════

@app.route("/recruiter")
def recruiter_dashboard():
    if "user" not in session or session["user"]["role"] != "recruiter":
        return redirect(url_for("login_page"))
    all_sessions = get_all_sessions()
    return render_template("recruiter.html", user=session["user"], all_sessions=all_sessions)


@app.route("/api/recruiter/leaderboard")
def recruiter_leaderboard():
    """Top scoring candidates across all sessions."""
    if "user" not in session or session["user"]["role"] != "recruiter":
        return jsonify({"error": "Unauthorized"}), 401

    all_sessions = get_all_sessions()
    completed = [s for s in all_sessions if s.get("status") == "completed" and s.get("report")]

    candidates = {}
    for s in completed:
        email = s.get("candidate_email", "unknown")
        name = s.get("candidate_name", "Unknown")
        report = s.get("report", {})
        score = report.get("overall_score", 0)
        phase = s.get("session_type", "technical")
        quit_reason = s.get("quit_reason")

        if email not in candidates:
            candidates[email] = {"name": name, "email": email, "sessions": [], "best_score": 0, "phases_completed": set()}

        candidates[email]["sessions"].append({
            "session_id": s.get("session_id"),
            "session_type": phase,
            "score": score,
            "date": s.get("started_at", "")[:10],
            "quit_reason": quit_reason
        })
        candidates[email]["best_score"] = max(candidates[email]["best_score"], score)
        candidates[email]["phases_completed"].add(phase)

    leaderboard = sorted(candidates.values(), key=lambda c: c["best_score"], reverse=True)
    for c in leaderboard:
        c["phases_completed"] = list(c["phases_completed"])

    return jsonify({"leaderboard": leaderboard, "total_candidates": len(leaderboard)})


# ═══════════════════════════════════════════════════════════════
# RECRUITER — JOB POSTINGS & RECRUITMENT PIPELINE
# ═══════════════════════════════════════════════════════════════

@app.route("/api/recruiter/jobs", methods=["GET"])
def list_jobs():
    if "user" not in session or session["user"]["role"] != "recruiter":
        return jsonify({"error": "Unauthorized"}), 401
    recruiter_email = session["user"]["email"]
    jobs = [j for j in job_postings.values() if j["recruiter_email"] == recruiter_email]
    for j in jobs:
        j["applicant_count"] = len([a for a in applications.values() if a["job_id"] == j["job_id"]])
    return jsonify({"jobs": sorted(jobs, key=lambda x: x["created_at"], reverse=True)})


@app.route("/api/recruiter/jobs", methods=["POST"])
def create_job():
    if "user" not in session or session["user"]["role"] != "recruiter":
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    job_id = str(uuid.uuid4())[:8]
    job_role = data.get("role", "Software Engineer")
    required_skills = [s.strip() for s in data.get("skills", "").split(",") if s.strip()]

    # Parse difficulty levels
    levels_str = data.get("levels", "1,2,3,4,5")
    num_questions = data.get("num_questions", 5)
    try:
        levels = [int(l.strip()) for l in levels_str.split(",") if l.strip()]
    except:
        levels = [1, 2, 3, 4, 5]

    # Expand levels to match num_questions
    if len(levels) < num_questions:
        expanded = []
        for i in range(num_questions):
            expanded.append(levels[int(i / num_questions * len(levels))])
        levels = expanded
    elif len(levels) > num_questions:
        levels = levels[:num_questions]

    # Generate screening test questions with difficulty levels
    questions = generate_screening_questions(job_role, num_questions, levels)

    job = {
        "job_id": job_id,
        "title": data.get("title", f"{job_role} Position"),
        "role": job_role,
        "description": data.get("description", ""),
        "required_skills": required_skills or ["Python", "Problem Solving", "Communication"],
        "recruiter_email": session["user"]["email"],
        "recruiter_name": session["user"]["name"],
        "created_at": datetime.utcnow().isoformat(),
        "status": "active",
        "screening_questions": questions,
        "pass_threshold": data.get("threshold", 55),
        "apply_link": f"/apply/{job_id}"
    }
    job_postings[job_id] = job

    # Save to disk
    jobs_file = DATA_DIR / "job_postings.json"
    all_jobs = {}
    if jobs_file.exists():
        with open(jobs_file, "r") as f:
            all_jobs = json.load(f)
    all_jobs[job_id] = job
    with open(jobs_file, "w") as f:
        json.dump(all_jobs, f, indent=2)

    return jsonify({"success": True, "job": job})


@app.route("/api/recruiter/applicants/<job_id>")
def list_applicants(job_id):
    if "user" not in session or session["user"]["role"] != "recruiter":
        return jsonify({"error": "Unauthorized"}), 401

    job_apps = [a for a in applications.values() if a["job_id"] == job_id]
    job_apps.sort(key=lambda a: a.get("screening", {}).get("combined_score", 0), reverse=True)
    return jsonify({"applicants": job_apps, "total": len(job_apps)})


# ═══════════════════════════════════════════════════════════════
# PUBLIC — CANDIDATE APPLICATION FLOW
# ═══════════════════════════════════════════════════════════════

@app.route("/apply/<job_id>")
def apply_page(job_id):
    """Public application page — no login required."""
    job = job_postings.get(job_id)
    if not job:
        # Try loading from disk
        jobs_file = DATA_DIR / "job_postings.json"
        if jobs_file.exists():
            with open(jobs_file, "r") as f:
                all_jobs = json.load(f)
            job = all_jobs.get(job_id)
            if job:
                job_postings[job_id] = job
    if not job:
        return "Job not found", 404
    return render_template("apply.html", job=job)


@app.route("/api/apply/<job_id>", methods=["POST"])
def submit_application(job_id):
    """Candidate submits application form with resume & profiles."""
    job = job_postings.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    # Get form data
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    phone = request.form.get("phone", "")
    linkedin_url = request.form.get("linkedin", "")
    github_url = request.form.get("github", "")
    portfolio_url = request.form.get("portfolio", "")
    resume_text = request.form.get("resume_text", "")

    if not name or not email:
        return jsonify({"error": "Name and email are required"}), 400

    # Handle resume file upload
    resume_file = request.files.get("resume_file")
    resume_filename = ""
    if resume_file and resume_file.filename:
        resume_filename = secure_filename(f"{email}_{resume_file.filename}")
        resume_file.save(str(UPLOADS_DIR / resume_filename))
        # If no resume_text provided, use filename as placeholder
        if not resume_text:
            resume_text = f"[Uploaded file: {resume_file.filename}]"

    app_id = str(uuid.uuid4())[:12]

    application = {
        "app_id": app_id,
        "job_id": job_id,
        "job_title": job["title"],
        "name": name,
        "email": email,
        "phone": phone,
        "linkedin": linkedin_url,
        "github": github_url,
        "portfolio": portfolio_url,
        "resume_text": resume_text,
        "resume_file": resume_filename,
        "applied_at": datetime.utcnow().isoformat(),
        "status": "applied",
        "screening": None
    }

    # ── Run ATS Resume Scoring ──────────────────────────────
    print(f"[Screening] Running ATS for {name}...")
    ats_result = score_resume_ats(resume_text, job["role"], job.get("required_skills"))

    # ── Run Experience Authenticity Check ────────────────────
    print(f"[Screening] Running authenticity check for {name}...")
    auth_result = evaluate_experience_authenticity(resume_text, linkedin_url, job["role"])

    # ── Score Social Profiles ───────────────────────────────
    social_result = score_social_profiles(linkedin_url, github_url, portfolio_url, resume_text)

    # Store partial screening (test not taken yet)
    application["screening"] = {
        "ats": ats_result,
        "authenticity": auth_result,
        "social": social_result,
        "test": None,
        "combined_score": 0,
        "status": "pending_test"
    }

    applications[app_id] = application

    # Create candidate account if not exists
    if email not in DEMO_USERS:
        DEMO_USERS[email] = {"password": "apply@123", "role": "candidate", "name": name}

    return jsonify({
        "success": True,
        "app_id": app_id,
        "ats_score": ats_result.get("ats_score", 0),
        "auth_score": auth_result.get("authenticity_score", 50),
        "social_score": social_result.get("overall_social_score", 0),
        "test_url": f"/screening-test/{app_id}",
        "message": "Application received! Please complete the screening test."
    })


# ═══════════════════════════════════════════════════════════════
# SCREENING TEST
# ═══════════════════════════════════════════════════════════════

@app.route("/screening-test/<app_id>")
def screening_test_page(app_id):
    """Screening test page — candidate takes the test."""
    app_data = applications.get(app_id)
    if not app_data:
        return "Application not found", 404

    job = job_postings.get(app_data["job_id"], {})
    questions = job.get("screening_questions", [])
    return render_template("screening_test.html", app=app_data, job=job, questions=questions)


@app.route("/api/screening-test/<app_id>", methods=["POST"])
def submit_screening_test(app_id):
    """Candidate submits screening test answers."""
    app_data = applications.get(app_id)
    if not app_data:
        return jsonify({"error": "Application not found"}), 404

    if app_data["screening"].get("status") == "completed":
        return jsonify({"error": "Test already submitted"}), 400

    data = request.get_json()
    answers = data.get("answers", {})

    job = job_postings.get(app_data["job_id"], {})
    questions = job.get("screening_questions", [])

    # Score the test
    test_result = score_screening_test(questions, answers)

    # Calculate combined screening score
    ats_result = app_data["screening"].get("ats", {})
    auth_result = app_data["screening"].get("authenticity", {})
    social_result = app_data["screening"].get("social", {})
    combined = calculate_combined_score(ats_result, auth_result, social_result, test_result)

    # Update application
    app_data["screening"]["test"] = test_result
    app_data["screening"]["combined_score"] = combined["combined_score"]
    app_data["screening"]["passed"] = combined["passed"]
    app_data["screening"]["breakdown"] = combined["breakdown"]
    app_data["screening"]["verdict"] = combined["verdict"]
    app_data["screening"]["status"] = "completed"
    app_data["status"] = "approved" if combined["passed"] else "rejected"

    return jsonify({
        "success": True,
        "test_result": test_result,
        "combined_score": combined["combined_score"],
        "passed": combined["passed"],
        "verdict": combined["verdict"],
        "breakdown": combined["breakdown"],
        "login_url": "/login" if combined["passed"] else None,
        "credentials": {"email": app_data["email"], "password": "apply@123"} if combined["passed"] else None
    })


# ═══════════════════════════════════════════════════════════════
# INTERVIEW ROUTES
# ═══════════════════════════════════════════════════════════════

@app.route("/interview")
def interview_page():
    if "user" not in session:
        return redirect(url_for("login_page"))
    session_id = request.args.get("session_id")
    if not session_id or session_id not in interview_sessions:
        return redirect(url_for("dashboard"))
    iv = interview_sessions[session_id]
    return render_template("interview.html",
                           user=session["user"],
                           session_id=session_id,
                           session_type=iv["session_type"],
                           role=iv.get("role", "Software Engineer"))


@app.route("/api/interview/start", methods=["POST"])
def start_interview():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    session_type = data.get("session_type", "technical")  # technical/behavioral/mock
    role = data.get("role", "Software Engineer")

    user = session["user"]
    session_id = str(uuid.uuid4())

    # Generate first question via AI
    opening = generate_opening_question(session_type, user["name"], role)

    iv = {
        "session_id": session_id,
        "candidate_name": user["name"],
        "candidate_email": user["email"],
        "session_type": session_type,
        "role": role,
        "status": "active",
        "started_at": datetime.utcnow().isoformat(),
        "question_num": 1,
        "current_question": opening,
        "conversation_history": [],
        "monitoring_events": [],
        "report": None
    }

    interview_sessions[session_id] = iv
    save_session_to_disk(session_id)

    return jsonify({
        "success": True,
        "session_id": session_id,
        "question": opening,
        "question_num": 1,
        "max_questions": MAX_QUESTIONS
    })


@app.route("/api/interview/answer", methods=["POST"])
def submit_answer():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    session_id = data.get("session_id")
    answer = data.get("answer", "").strip()
    answer_type = data.get("answer_type", "text")   # text/code/verbal

    iv = interview_sessions.get(session_id)
    if not iv:
        iv = load_session_from_disk(session_id)
        if not iv:
            return jsonify({"error": "Session not found"}), 404
        interview_sessions[session_id] = iv

    current_q = iv["current_question"]
    q_num = iv["question_num"]

    # Get evaluation + next question from AI
    result = evaluate_and_adapt(
        session_type=iv["session_type"],
        conversation_history=iv["conversation_history"],
        current_question=current_q,
        candidate_answer=answer,
        answer_type=answer_type,
        question_num=q_num,
        role=iv.get("role", "Software Engineer")
    )

    evaluation = result.get("evaluation", {})
    next_q = result.get("next_question", {})

    # Store completed QA in history
    iv["conversation_history"].append({
        "question_num": q_num,
        "question": current_q.get("question", ""),
        "topic": current_q.get("topic", ""),
        "difficulty": current_q.get("difficulty", 1),
        "answer": answer,
        "answer_type": answer_type,
        "overall_score": evaluation.get("overall", 65),
        "evaluation": evaluation,
        "timestamp": datetime.utcnow().isoformat()
    })

    iv["question_num"] = q_num + 1

    # ── Poor performance / irrelevant answer detection ─────────
    POOR_SCORE_THRESHOLD = 30       # Score below this = poor answer
    IRRELEVANT_THRESHOLD = 15       # Score below this = irrelevant/garbage
    MAX_CONSECUTIVE_POOR = 3        # Auto-quit after this many consecutive poor answers

    overall_score = evaluation.get("overall", 65)
    correctness = evaluation.get("correctness", 65)

    # Initialize tracking if not present
    if "consecutive_poor" not in iv:
        iv["consecutive_poor"] = 0
    if "total_poor" not in iv:
        iv["total_poor"] = 0

    # Check if this answer is poor or irrelevant
    is_irrelevant = overall_score <= IRRELEVANT_THRESHOLD or correctness <= IRRELEVANT_THRESHOLD
    is_poor = overall_score <= POOR_SCORE_THRESHOLD

    if is_irrelevant or is_poor:
        iv["consecutive_poor"] += 1
        iv["total_poor"] += 1
    else:
        iv["consecutive_poor"] = 0  # Reset streak on a decent answer

    # Auto-quit: too many consecutive poor/irrelevant answers
    should_auto_quit = iv["consecutive_poor"] >= MAX_CONSECUTIVE_POOR

    if should_auto_quit:
        iv["status"] = "generating_report"
        iv["quit_reason"] = "poor_performance"
        save_session_to_disk(session_id)

        report = generate_final_report(
            session_type=iv["session_type"],
            conversation_history=iv["conversation_history"],
            candidate_name=iv["candidate_name"],
            role=iv.get("role", "Software Engineer")
        )
        iv["status"] = "completed"
        iv["completed_at"] = datetime.utcnow().isoformat()
        iv["report"] = report
        save_session_to_disk(session_id)

        return jsonify({
            "success": True,
            "interview_complete": True,
            "auto_quit": True,
            "quit_reason": "poor_performance",
            "message": "Interview ended due to consistently poor or irrelevant answers.",
            "evaluation": evaluation,
            "session_id": session_id
        })

    # ── Check if interview should end (normal) ────────────────
    max_reached = q_num >= MAX_QUESTIONS
    min_reached = q_num >= MIN_QUESTIONS
    end_requested = data.get("end_interview", False)

    if max_reached or (min_reached and end_requested):
        iv["status"] = "generating_report"
        save_session_to_disk(session_id)

        # Generate final LLM report
        report = generate_final_report(
            session_type=iv["session_type"],
            conversation_history=iv["conversation_history"],
            candidate_name=iv["candidate_name"],
            role=iv.get("role", "Software Engineer")
        )
        iv["status"] = "completed"
        iv["completed_at"] = datetime.utcnow().isoformat()
        iv["report"] = report
        save_session_to_disk(session_id)

        return jsonify({
            "success": True,
            "interview_complete": True,
            "evaluation": evaluation,
            "session_id": session_id
        })

    # ── Continue interview ─────────────────────────────────────
    iv["current_question"] = next_q
    save_session_to_disk(session_id)

    return jsonify({
        "success": True,
        "interview_complete": False,
        "evaluation": evaluation,
        "next_question": next_q,
        "question_num": iv["question_num"],
        "max_questions": MAX_QUESTIONS,
        "progress_pct": int((iv["question_num"] - 1) / MAX_QUESTIONS * 100),
        "poor_answer_warning": iv["consecutive_poor"] >= 2,
        "consecutive_poor": iv["consecutive_poor"]
    })


@app.route("/api/interview/end", methods=["POST"])
def end_interview_early():
    """End interview early and generate report."""
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    session_id = data.get("session_id")
    iv = interview_sessions.get(session_id) or load_session_from_disk(session_id)

    if not iv or not iv.get("conversation_history"):
        return jsonify({"error": "No data to generate report from"}), 400

    report = generate_final_report(
        session_type=iv["session_type"],
        conversation_history=iv["conversation_history"],
        candidate_name=iv["candidate_name"],
        role=iv.get("role", "Software Engineer")
    )
    iv["status"] = "completed"
    iv["completed_at"] = datetime.utcnow().isoformat()
    iv["report"] = report
    interview_sessions[session_id] = iv
    save_session_to_disk(session_id)

    return jsonify({"success": True, "session_id": session_id})


# ═══════════════════════════════════════════════════════════════
# INTERVIEW STATE (used by frontend JS on load)
# ═══════════════════════════════════════════════════════════════

@app.route("/api/interview/state")
def interview_state():
    """Get current interview state (current question, progress)."""
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    session_id = request.args.get("session_id")
    iv = interview_sessions.get(session_id) or load_session_from_disk(session_id)
    if not iv:
        return jsonify({"error": "Session not found"}), 404

    return jsonify({
        "question": iv.get("current_question"),
        "question_num": iv.get("question_num", 1),
        "max_questions": MAX_QUESTIONS,
        "session_type": iv.get("session_type"),
        "status": iv.get("status"),
        "answered": len(iv.get("conversation_history", []))
    })


@app.route("/api/interview/current")
def interview_current():
    """Alias for /api/interview/state."""
    return interview_state()


# ═══════════════════════════════════════════════════════════════
# MONITORING
# ═══════════════════════════════════════════════════════════════

@app.route("/api/monitor/event", methods=["POST"])
def monitor_event():
    """Record a monitoring event (tab switch, copy-paste, etc.)."""
    data = request.get_json()
    session_id = data.get("session_id")
    event_type = data.get("event_type")
    details = data.get("details", {})

    iv = interview_sessions.get(session_id)
    if iv:
        iv["monitoring_events"].append({
            "type": event_type,
            "details": details,
            "timestamp": datetime.utcnow().isoformat()
        })
        save_session_to_disk(session_id)

    return jsonify({"success": True})


# ═══════════════════════════════════════════════════════════════
# REPORT
# ═══════════════════════════════════════════════════════════════

@app.route("/report/<session_id>")
def report_page(session_id):
    if "user" not in session:
        return redirect(url_for("login_page"))

    iv = interview_sessions.get(session_id) or load_session_from_disk(session_id)
    if not iv:
        return redirect(url_for("dashboard"))

    # Allow recruiter to view any report
    user = session["user"]
    if user["role"] == "candidate" and iv.get("candidate_email") != user["email"]:
        return redirect(url_for("dashboard"))

    return render_template("report.html",
                           user=user,
                           session_data=iv,
                           report=(iv.get("report") or {}))


@app.route("/api/report/<session_id>")
def api_get_report(session_id):
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    iv = interview_sessions.get(session_id) or load_session_from_disk(session_id)
    if not iv:
        return jsonify({"error": "Session not found"}), 404

    return jsonify({
        "session": {
            "session_id": session_id,
            "session_type": iv.get("session_type"),
            "candidate_name": iv.get("candidate_name"),
            "role": iv.get("role"),
            "started_at": iv.get("started_at"),
            "completed_at": iv.get("completed_at"),
            "status": iv.get("status"),
            "total_questions": len(iv.get("conversation_history", [])),
            "monitoring_events": iv.get("monitoring_events", [])
        },
        "report": iv.get("report", {}),
        "history": iv.get("conversation_history", [])
    })


# ═══════════════════════════════════════════════════════════════
# STT — ElevenLabs Scribe v1 (cloud, high-accuracy)
# ═══════════════════════════════════════════════════════════════

@app.route("/api/stt/transcribe", methods=["POST"])
def stt_transcribe():
    """Transcribe audio using ElevenLabs API."""
    import requests
    
    if "audio" not in request.files:
        return jsonify({"error": "No audio file provided"}), 400

    audio_file = request.files["audio"]
    audio_bytes = audio_file.read()

    print(f"[STT] Received audio: {len(audio_bytes)} bytes")
    if len(audio_bytes) < 100:
        print(f"[STT] Rejected — too small")
        return jsonify({"transcript": "", "note": "Audio too short"})

    try:
        from config import ELEVENLABS_API_KEY
        
        # Scribe v1 API endpoint
        url = "https://api.elevenlabs.io/v1/speech-to-text"
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY
        }
        
        # Determine filename and MIME type
        filename = audio_file.filename or "recording.wav"
        if filename.endswith('.webm'):
            mime = 'audio/webm'
        else:
            mime = 'audio/wav'
        
        print(f"[ElevenLabs STT] Sending {len(audio_bytes)} bytes, filename={filename}")
        
        files = {
            'file': (filename, audio_bytes, mime)
        }
        
        data = {
            "model_id": "scribe_v1",
            "language_code": "en",
            "tag_audio_events": "false",
            "diarize": "false"
        }
        
        resp = requests.post(url, headers=headers, data=data, files=files, timeout=30)
        
        if resp.status_code == 200:
            result = resp.json()
            transcript = result.get("text", "")
            
            print(f"[ElevenLabs STT] Raw: {result}")
            
            # Strip audio event tags like (beatboxing), (tiktok zvocok) etc.
            import re
            transcript = re.sub(r'\([^)]*\)', '', transcript)
            transcript = transcript.replace("\u266a", "").strip()
            
            # Reject non-English transcripts: if >15% chars are non-ASCII,
            # it's background audio from another app (Korean video, etc.)
            if transcript:
                non_latin = sum(1 for c in transcript if ord(c) > 127)
                if non_latin / len(transcript) > 0.15:
                    print(f"[ElevenLabs STT] Rejected non-English: '{transcript}'")
                    transcript = ""
            
            if transcript.lower() in ["trial.", "trial", ""]:
                transcript = ""
            
            print(f"[ElevenLabs STT] Final: '{transcript}'")
            return jsonify({"transcript": transcript, "success": True, "method": "elevenlabs"})
        else:
            print(f"[ElevenLabs STT error] {resp.status_code}: {resp.text}")
            return jsonify({"error": f"API error {resp.status_code}: {resp.text}", "transcript": ""}), 500

    except Exception as e:
        import traceback
        print("[ElevenLabs STT Exception]", traceback.format_exc())
        return jsonify({"error": str(e), "transcript": ""}), 500


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print("[AI Interview Platform] Starting...")
    print(f"[AI Interview Platform] Running at: http://localhost:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG)
