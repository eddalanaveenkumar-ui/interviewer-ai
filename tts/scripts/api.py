"""
api.py — Flask REST API for TTS
Endpoint: POST /api/tts/speak
"""

import os
import uuid
import asyncio
from pathlib import Path
from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS

# Import TTS engine
import sys
sys.path.append(str(Path(__file__).parent))
from tts_engine import speak, EDGE_TTS_VOICES

app = Flask(__name__, template_folder="../templates", static_folder="../static")
CORS(app)

OUTPUT_DIR = Path(__file__).parent.parent / "audio_output"
OUTPUT_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    """Serve the TTS demo page."""
    return render_template("tts_demo.html", voices=EDGE_TTS_VOICES)


@app.route("/api/tts/speak", methods=["POST"])
def tts_speak():
    """
    Convert text to speech and return audio file.

    Request JSON:
    {
        "text": "Hello World",
        "engine": "edge",           // optional: "edge", "silero", "coqui"
        "voice": "en-US-JennyNeural", // optional (edge only)
        "speed": 1.0                // optional: 0.5 - 2.0
    }
    """
    data = request.get_json()

    if not data or "text" not in data:
        return jsonify({"error": "Missing 'text' field in request body"}), 400

    text = data.get("text", "").strip()
    engine = data.get("engine", "edge")
    voice = data.get("voice", "en-US-JennyNeural")
    speed = float(data.get("speed", 1.0))

    if not text:
        return jsonify({"error": "Text cannot be empty"}), 400

    if len(text) > 5000:
        return jsonify({"error": "Text too long (max 5000 characters)"}), 400

    # Generate unique filename
    filename = f"{uuid.uuid4()}.mp3" if engine == "edge" else f"{uuid.uuid4()}.wav"
    output_path = str(OUTPUT_DIR / filename)

    # Generate TTS audio
    result = speak(text, engine=engine, voice=voice, speed=speed, output_file=output_path)

    if not result or not os.path.exists(result):
        return jsonify({"error": "TTS generation failed"}), 500

    # Determine MIME type
    mime_type = "audio/mpeg" if result.endswith(".mp3") else "audio/wav"

    return send_file(result, mimetype=mime_type, as_attachment=False,
                     download_name=filename)


@app.route("/api/tts/voices", methods=["GET"])
def list_voices():
    """Return available voice options."""
    return jsonify({
        "edge_tts": EDGE_TTS_VOICES,
        "engines": ["edge", "silero", "coqui"],
        "default_engine": "edge",
        "default_voice": "en-US-JennyNeural"
    })


@app.route("/api/tts/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "service": "TTS API", "version": "1.0.0"})


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("🔊 TTS API Server starting...")
    print("📡 API running at: http://localhost:5050")
    print("🎤 Demo UI at: http://localhost:5050/")
    app.run(host="0.0.0.0", port=5050, debug=True)
