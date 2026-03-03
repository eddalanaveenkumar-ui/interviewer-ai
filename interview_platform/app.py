"""
app.py — Main Flask Application
AI-Driven Interview Platform
"""

import os, sys, json, uuid
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from config import SECRET_KEY, DEBUG, PORT, DEMO_USERS, MAX_QUESTIONS, MIN_QUESTIONS
from backend.ai_engine import (
    generate_opening_question,
    evaluate_and_adapt,
    generate_final_report
)

app = Flask(__name__)
app.secret_key = SECRET_KEY
CORS(app)

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# ── In-Memory Session Store ─────────────────────────────────
interview_sessions = {}   # session_id → session data


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
# DASHBOARD
# ═══════════════════════════════════════════════════════════════

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login_page"))
    user = session["user"]
    past = get_all_sessions_for_user(user["email"]) if user["role"] == "candidate" else get_all_sessions()
    return render_template("dashboard.html", user=user, past_sessions=past[:5])


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

    # ── Check if interview should end ──────────────────────────
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
        "progress_pct": int((iv["question_num"] - 1) / MAX_QUESTIONS * 100)
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
# STT — OpenAI Whisper (open-source, high-quality)
# ═══════════════════════════════════════════════════════════════

_whisper_model = None   # lazy-loaded on first request

def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        import whisper
        print("[Whisper] Loading 'base' model (first time — downloading ~74MB)…")
        _whisper_model = whisper.load_model("base")
        print("[Whisper] Model ready.")
    return _whisper_model


@app.route("/api/stt/transcribe", methods=["POST"])
def stt_transcribe():
    """Transcribe audio using OpenAI Whisper (open-source, high accuracy)."""
    import wave, io, tempfile, os
    import numpy as np

    if "audio" not in request.files:
        return jsonify({"error": "No audio file provided"}), 400

    audio_file = request.files["audio"]
    audio_bytes = audio_file.read()

    if len(audio_bytes) < 500:
        return jsonify({"transcript": "", "note": "Audio too short"})

    try:
        model = get_whisper_model()

        # --- Path 1: Browser-recorded PCM WAV (no ffmpeg needed) ---
        try:
            with wave.open(io.BytesIO(audio_bytes)) as wf:
                n_channels = wf.getnchannels()
                sr          = wf.getframerate()
                frames      = wf.readframes(wf.getnframes())

            # Convert to float32 mono numpy array
            samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            if n_channels == 2:                        # stereo → mono
                samples = samples.reshape(-1, 2).mean(axis=1)

            # Resample to 16 kHz if needed (Whisper expects 16 kHz)
            if sr != 16000 and len(samples) > 0:
                import whisper.audio as wa
                samples = wa.resample(samples, sr, 16000)

            result = model.transcribe(samples, language="en", fp16=False)
            transcript = result["text"].strip()
            return jsonify({"transcript": transcript, "success": True, "method": "wav_numpy"})

        except (wave.Error, EOFError):
            pass   # not a WAV — fall through to temp-file method

        # --- Path 2: Any audio format via temp file (needs ffmpeg) ---
        suffix = ".webm"
        fn = audio_file.filename or ""
        if "." in fn:
            suffix = os.path.splitext(fn)[-1] or ".webm"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            result = model.transcribe(tmp_path, language="en", fp16=False)
            transcript = result["text"].strip()
            return jsonify({"transcript": transcript, "success": True, "method": "tmpfile"})
        finally:
            try: os.unlink(tmp_path)
            except: pass

    except Exception as e:
        import traceback
        print("[Whisper STT error]", traceback.format_exc())
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
