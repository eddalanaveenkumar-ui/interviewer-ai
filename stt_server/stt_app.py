"""
STT Server — Dedicated Speech-to-Text service using ElevenLabs Scribe API
Runs on port 5056, separate from the main interview platform.

Features:
  - POST /api/stt/transcribe  — Transcribe audio via ElevenLabs
  - GET  /                     — Audio recordings player page
  - GET  /api/recordings       — List all saved recordings as JSON
  - GET  /audio/<filename>     — Serve a saved audio file
"""

import os
import re
import sys
import json
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, render_template_string
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)

# ── Config ──────────────────────────────────────────────────
ELEVENLABS_API_KEY = os.getenv(
    "ELEVENLABS_API_KEY",
    "sk_731f5124d148dce5da10b34d8789430a32317b8f5dbccdb7"
)
ELEVENLABS_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"
PORT = int(os.getenv("STT_PORT", 5056))

# Directory to save audio recordings
RECORDINGS_DIR = os.path.join(os.path.dirname(__file__), "recordings")
os.makedirs(RECORDINGS_DIR, exist_ok=True)

# Metadata file for recordings
METADATA_FILE = os.path.join(RECORDINGS_DIR, "metadata.json")


def load_metadata():
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_metadata(data):
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── Health ──────────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "stt-elevenlabs"})


# ── Transcribe ──────────────────────────────────────────────
@app.route("/api/stt/transcribe", methods=["POST"])
def transcribe():
    if "audio" not in request.files:
        return jsonify({"error": "No audio file provided", "transcript": ""}), 400

    audio_file = request.files["audio"]
    audio_bytes = audio_file.read()
    session_id = request.form.get("session_id", "unknown")

    print(f"[STT] Received {len(audio_bytes)} bytes (session: {session_id})")

    if len(audio_bytes) < 100:
        return jsonify({"transcript": "", "note": "Audio too short", "success": True})

    # Determine extension and MIME
    filename = audio_file.filename or "recording.webm"
    if filename.endswith('.webm'):
        mime, ext = 'audio/webm', '.webm'
    elif filename.endswith('.ogg'):
        mime, ext = 'audio/ogg', '.ogg'
    elif filename.endswith('.wav'):
        mime, ext = 'audio/wav', '.wav'
    else:
        mime, ext = 'audio/webm', '.webm'

    # Save the audio recording
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved_filename = f"{session_id}_{timestamp}{ext}"
    saved_path = os.path.join(RECORDINGS_DIR, saved_filename)

    with open(saved_path, "wb") as f:
        f.write(audio_bytes)

    print(f"[STT] Saved: {saved_filename} ({len(audio_bytes)} bytes)")

    try:
        # Call ElevenLabs Scribe v1 API
        headers = {"xi-api-key": ELEVENLABS_API_KEY}
        files = {'file': (filename, audio_bytes, mime)}
        data = {
            "model_id": "scribe_v1",
            "language_code": "en",
            "tag_audio_events": "false",
            "diarize": "false"
        }

        print(f"[STT] Sending to ElevenLabs: {filename} ({mime})")

        resp = requests.post(
            ELEVENLABS_STT_URL,
            headers=headers,
            data=data,
            files=files,
            timeout=30
        )

        transcript = ""

        if resp.status_code == 200:
            result = resp.json()
            transcript = result.get("text", "")
            print(f"[STT] ElevenLabs raw: '{transcript}'")

            # Cleanup filters
            transcript = re.sub(r'\([^)]*\)', '', transcript)
            transcript = transcript.replace("♪", "").strip()

            if transcript:
                non_latin = sum(1 for c in transcript if ord(c) > 127)
                if len(transcript) > 0 and non_latin / len(transcript) > 0.15:
                    print(f"[STT] Rejected non-English: '{transcript}'")
                    transcript = ""

            if transcript.lower().strip() in ["trial.", "trial", ""]:
                transcript = ""

            transcript = re.sub(r'\s+', ' ', transcript).strip()
            print(f"[STT] Final: '{transcript}'")
        else:
            print(f"[STT] ElevenLabs error {resp.status_code}: {resp.text}")

        # Update metadata with transcript
        metadata = load_metadata()
        metadata.append({
            "filename": saved_filename,
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "size_bytes": len(audio_bytes),
            "transcript": transcript,
            "mime": mime
        })
        save_metadata(metadata)

        return jsonify({
            "transcript": transcript,
            "success": True,
            "method": "elevenlabs",
            "audio_saved": saved_filename
        })

    except requests.Timeout:
        print("[STT] ElevenLabs API timeout")
        return jsonify({"error": "Transcription timed out", "transcript": "", "success": False}), 504

    except Exception as e:
        import traceback
        print(f"[STT] Exception: {traceback.format_exc()}")
        return jsonify({"error": str(e), "transcript": "", "success": False}), 500


# ── Serve saved audio files ─────────────────────────────────
@app.route("/audio/<filename>")
def serve_audio(filename):
    return send_from_directory(RECORDINGS_DIR, filename)


# ── List recordings API ─────────────────────────────────────
@app.route("/api/recordings", methods=["GET"])
def list_recordings():
    session_filter = request.args.get("session_id")
    metadata = load_metadata()
    if session_filter:
        metadata = [r for r in metadata if r["session_id"] == session_filter]
    metadata.reverse()  # newest first
    return jsonify({"recordings": metadata})


# ── Delete all recordings ───────────────────────────────────
@app.route("/api/recordings/clear", methods=["POST"])
def clear_recordings():
    metadata = load_metadata()
    for rec in metadata:
        path = os.path.join(RECORDINGS_DIR, rec["filename"])
        if os.path.exists(path):
            os.remove(path)
    save_metadata([])
    return jsonify({"status": "cleared", "deleted": len(metadata)})


# ── Audio Player Page ───────────────────────────────────────
@app.route("/")
def audio_player_page():
    return render_template_string(AUDIO_PLAYER_HTML)


AUDIO_PLAYER_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Interview Audio Recordings — STT Server</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        :root {
            --bg-dark: #0f1117;
            --bg-surface: #1a1d27;
            --bg-card: #22253a;
            --bg-hover: #2a2e42;
            --text-primary: #f0f2f5;
            --text-secondary: #a0a4b8;
            --text-muted: #6b6f85;
            --accent: #6366f1;
            --accent-glow: rgba(99, 102, 241, 0.25);
            --success: #10b981;
            --danger: #ef4444;
            --warning: #f59e0b;
            --border: #2e3247;
            --radius: 12px;
        }

        body {
            font-family: 'Inter', -apple-system, sans-serif;
            background: var(--bg-dark);
            color: var(--text-primary);
            min-height: 100vh;
        }

        /* Header */
        .header {
            background: linear-gradient(135deg, var(--bg-surface), var(--bg-card));
            border-bottom: 1px solid var(--border);
            padding: 1.5rem 2rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .header h1 {
            font-size: 1.4rem;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 0.6rem;
        }

        .header h1 span { font-size: 1.6rem; }

        .header-badge {
            background: var(--accent);
            color: #fff;
            font-size: 0.7rem;
            font-weight: 700;
            padding: 3px 10px;
            border-radius: 20px;
            letter-spacing: 0.05em;
        }

        .header-actions {
            display: flex;
            gap: 0.75rem;
            align-items: center;
        }

        .btn {
            font-family: inherit;
            font-size: 0.82rem;
            font-weight: 600;
            padding: 8px 16px;
            border-radius: 8px;
            border: 1px solid var(--border);
            background: var(--bg-card);
            color: var(--text-primary);
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 0.4rem;
        }

        .btn:hover {
            background: var(--bg-hover);
            border-color: var(--accent);
        }

        .btn-danger {
            background: rgba(239, 68, 68, 0.15);
            border-color: rgba(239, 68, 68, 0.3);
            color: var(--danger);
        }

        .btn-danger:hover {
            background: rgba(239, 68, 68, 0.25);
        }

        /* Stats bar */
        .stats {
            display: flex;
            gap: 1.5rem;
            padding: 1rem 2rem;
            background: var(--bg-surface);
            border-bottom: 1px solid var(--border);
        }

        .stat {
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .stat-icon { font-size: 1.2rem; }

        .stat-label {
            font-size: 0.75rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }

        .stat-value {
            font-size: 1.1rem;
            font-weight: 700;
            color: var(--accent);
        }

        /* Filter bar */
        .filter-bar {
            padding: 1rem 2rem;
            display: flex;
            gap: 0.75rem;
            align-items: center;
        }

        .filter-bar input {
            font-family: inherit;
            font-size: 0.85rem;
            padding: 8px 14px;
            border-radius: 8px;
            border: 1px solid var(--border);
            background: var(--bg-card);
            color: var(--text-primary);
            width: 300px;
            outline: none;
            transition: border-color 0.2s;
        }

        .filter-bar input:focus {
            border-color: var(--accent);
            box-shadow: 0 0 0 3px var(--accent-glow);
        }

        .filter-bar input::placeholder { color: var(--text-muted); }

        /* Recordings list */
        .recordings {
            padding: 0 2rem 2rem;
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }

        .recording-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 1.2rem 1.5rem;
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
            transition: all 0.2s;
        }

        .recording-card:hover {
            border-color: var(--accent);
            box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3);
        }

        .rec-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .rec-info {
            display: flex;
            align-items: center;
            gap: 1rem;
        }

        .rec-num {
            font-size: 0.7rem;
            font-weight: 700;
            color: var(--text-muted);
            background: var(--bg-dark);
            padding: 3px 10px;
            border-radius: 6px;
            letter-spacing: 0.08em;
        }

        .rec-session {
            font-size: 0.78rem;
            color: var(--accent);
            font-weight: 600;
            font-family: monospace;
        }

        .rec-time {
            font-size: 0.75rem;
            color: var(--text-muted);
        }

        .rec-size {
            font-size: 0.72rem;
            color: var(--text-muted);
            background: var(--bg-dark);
            padding: 2px 8px;
            border-radius: 4px;
        }

        .rec-transcript {
            background: var(--bg-dark);
            border-radius: 8px;
            padding: 0.85rem 1rem;
            font-size: 0.88rem;
            line-height: 1.5;
            color: var(--text-secondary);
            border-left: 3px solid var(--accent);
        }

        .rec-transcript.empty {
            color: var(--text-muted);
            font-style: italic;
            border-left-color: var(--warning);
        }

        .rec-audio {
            width: 100%;
        }

        .rec-audio audio {
            width: 100%;
            height: 42px;
            border-radius: 8px;
            outline: none;
        }

        /* Empty state */
        .empty-state {
            text-align: center;
            padding: 4rem 2rem;
            color: var(--text-muted);
        }

        .empty-state .icon { font-size: 4rem; margin-bottom: 1rem; }
        .empty-state h2 { font-size: 1.2rem; color: var(--text-secondary); margin-bottom: 0.5rem; }
        .empty-state p { font-size: 0.88rem; }

        /* Loading */
        .loading {
            text-align: center;
            padding: 3rem;
            color: var(--text-muted);
            font-size: 0.9rem;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .spinner {
            display: inline-block;
            width: 24px;
            height: 24px;
            border: 3px solid var(--border);
            border-top-color: var(--accent);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin-bottom: 0.5rem;
        }

        /* Session group heading */
        .session-group {
            font-size: 0.78rem;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.06em;
            padding: 0.5rem 0;
            margin-top: 0.5rem;
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .session-group .count {
            background: var(--accent);
            color: #fff;
            font-size: 0.65rem;
            padding: 1px 7px;
            border-radius: 10px;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1><span>🎙️</span> Interview Audio Recordings <span class="header-badge">STT Server</span></h1>
        <div class="header-actions">
            <button class="btn" onclick="loadRecordings()">🔄 Refresh</button>
            <button class="btn btn-danger" onclick="clearAll()">🗑️ Clear All</button>
        </div>
    </div>

    <div class="stats" id="stats">
        <div class="stat">
            <span class="stat-icon">📁</span>
            <div>
                <div class="stat-label">Total Recordings</div>
                <div class="stat-value" id="stat-total">—</div>
            </div>
        </div>
        <div class="stat">
            <span class="stat-icon">💬</span>
            <div>
                <div class="stat-label">With Transcript</div>
                <div class="stat-value" id="stat-transcribed">—</div>
            </div>
        </div>
        <div class="stat">
            <span class="stat-icon">🗂️</span>
            <div>
                <div class="stat-label">Sessions</div>
                <div class="stat-value" id="stat-sessions">—</div>
            </div>
        </div>
        <div class="stat">
            <span class="stat-icon">💾</span>
            <div>
                <div class="stat-label">Total Size</div>
                <div class="stat-value" id="stat-size">—</div>
            </div>
        </div>
    </div>

    <div class="filter-bar">
        <input type="text" id="search" placeholder="🔍 Filter by session ID or transcript…" oninput="filterRecordings()">
        <button class="btn" onclick="playAll()">▶️ Play All</button>
    </div>

    <div class="recordings" id="recordings">
        <div class="loading"><div class="spinner"></div><br>Loading recordings…</div>
    </div>

    <script>
        let allRecordings = [];
        let currentlyPlaying = null;

        async function loadRecordings() {
            const container = document.getElementById('recordings');
            container.innerHTML = '<div class="loading"><div class="spinner"></div><br>Loading recordings…</div>';

            try {
                const res = await fetch('/api/recordings');
                const data = await res.json();
                allRecordings = data.recordings || [];
                renderRecordings(allRecordings);
                updateStats(allRecordings);
            } catch (err) {
                container.innerHTML = '<div class="empty-state"><div class="icon">❌</div><h2>Error loading recordings</h2><p>' + err.message + '</p></div>';
            }
        }

        function updateStats(recs) {
            document.getElementById('stat-total').textContent = recs.length;
            document.getElementById('stat-transcribed').textContent = recs.filter(r => r.transcript).length;

            const sessions = new Set(recs.map(r => r.session_id));
            document.getElementById('stat-sessions').textContent = sessions.size;

            const totalBytes = recs.reduce((sum, r) => sum + (r.size_bytes || 0), 0);
            document.getElementById('stat-size').textContent = formatSize(totalBytes);
        }

        function formatSize(bytes) {
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
            return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
        }

        function formatTime(iso) {
            try {
                const d = new Date(iso);
                return d.toLocaleString('en-US', {
                    month: 'short', day: 'numeric',
                    hour: '2-digit', minute: '2-digit', second: '2-digit'
                });
            } catch { return iso; }
        }

        function renderRecordings(recs) {
            const container = document.getElementById('recordings');

            if (recs.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="icon">🎙️</div>
                        <h2>No recordings yet</h2>
                        <p>Audio recordings from interview sessions will appear here.<br>
                        Start an interview and use voice recording to see them.</p>
                    </div>`;
                return;
            }

            // Group by session
            const grouped = {};
            recs.forEach(r => {
                if (!grouped[r.session_id]) grouped[r.session_id] = [];
                grouped[r.session_id].push(r);
            });

            let html = '';
            let globalIdx = 0;

            for (const [sessionId, sessionRecs] of Object.entries(grouped)) {
                const shortId = sessionId.length > 12
                    ? sessionId.substring(0, 8) + '…' + sessionId.slice(-4)
                    : sessionId;

                html += `<div class="session-group">
                    🗂️ Session: ${shortId}
                    <span class="count">${sessionRecs.length} clip${sessionRecs.length > 1 ? 's' : ''}</span>
                </div>`;

                sessionRecs.forEach((rec, idx) => {
                    globalIdx++;
                    const hasTranscript = rec.transcript && rec.transcript.trim();
                    html += `
                    <div class="recording-card" id="rec-${globalIdx}">
                        <div class="rec-header">
                            <div class="rec-info">
                                <span class="rec-num">#${globalIdx}</span>
                                <span class="rec-time">${formatTime(rec.timestamp)}</span>
                                <span class="rec-size">${formatSize(rec.size_bytes)}</span>
                            </div>
                        </div>
                        <div class="rec-transcript ${hasTranscript ? '' : 'empty'}">
                            ${hasTranscript
                                ? '💬 "' + rec.transcript + '"'
                                : '⚠️ No transcript (silence or noise detected)'}
                        </div>
                        <div class="rec-audio">
                            <audio controls preload="none" data-idx="${globalIdx}">
                                <source src="/audio/${rec.filename}" type="${rec.mime || 'audio/webm'}">
                            </audio>
                        </div>
                    </div>`;
                });
            }

            container.innerHTML = html;
        }

        function filterRecordings() {
            const query = document.getElementById('search').value.toLowerCase();
            if (!query) {
                renderRecordings(allRecordings);
                return;
            }
            const filtered = allRecordings.filter(r =>
                (r.session_id || '').toLowerCase().includes(query) ||
                (r.transcript || '').toLowerCase().includes(query)
            );
            renderRecordings(filtered);
        }

        async function clearAll() {
            if (!confirm('Delete all audio recordings? This cannot be undone.')) return;
            try {
                await fetch('/api/recordings/clear', { method: 'POST' });
                loadRecordings();
            } catch (err) {
                alert('Error: ' + err.message);
            }
        }

        function playAll() {
            const audios = document.querySelectorAll('audio');
            if (audios.length === 0) return;

            let idx = 0;
            function playNext() {
                if (idx >= audios.length) return;
                const a = audios[idx];
                a.scrollIntoView({ behavior: 'smooth', block: 'center' });
                a.closest('.recording-card').style.borderColor = 'var(--success)';
                a.play();
                a.onended = () => {
                    a.closest('.recording-card').style.borderColor = '';
                    idx++;
                    playNext();
                };
            }
            playNext();
        }

        // Load on page load
        loadRecordings();

        // Auto-refresh every 10 seconds
        setInterval(loadRecordings, 10000);
    </script>
</body>
</html>
"""


# ── Mic Test Page ───────────────────────────────────────────
@app.route("/mic-test")
def mic_test_page():
    return render_template_string(MIC_TEST_HTML)


# Store preferred device ID
preferred_device = {"id": None}


@app.route("/api/preferred-device", methods=["GET"])
def get_preferred_device():
    return jsonify({"device_id": preferred_device["id"]})


@app.route("/api/preferred-device", methods=["POST"])
def set_preferred_device():
    data = request.get_json()
    preferred_device["id"] = data.get("device_id")
    print(f"[STT] Preferred mic device set: {preferred_device['id']}")
    return jsonify({"status": "ok", "device_id": preferred_device["id"]})


MIC_TEST_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🎙️ Microphone Test — STT Server</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --bg: #0f1117; --surface: #1a1d27; --card: #22253a;
            --text: #f0f2f5; --text2: #a0a4b8; --muted: #6b6f85;
            --accent: #6366f1; --success: #10b981; --danger: #ef4444;
            --warning: #f59e0b; --border: #2e3247; --radius: 12px;
        }
        body { font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }

        .header {
            background: linear-gradient(135deg, var(--surface), var(--card));
            border-bottom: 1px solid var(--border);
            padding: 1.5rem 2rem;
            display: flex; align-items: center; justify-content: space-between;
        }
        .header h1 { font-size: 1.4rem; font-weight: 700; }
        .header a { color: var(--accent); text-decoration: none; font-size: 0.85rem; font-weight: 600; }

        .container { max-width: 800px; margin: 0 auto; padding: 2rem; }

        .section {
            background: var(--card); border: 1px solid var(--border);
            border-radius: var(--radius); padding: 1.5rem; margin-bottom: 1.5rem;
        }
        .section h2 { font-size: 1.1rem; margin-bottom: 1rem; display: flex; align-items: center; gap: 0.5rem; }

        /* Device list */
        .device-list { display: flex; flex-direction: column; gap: 0.5rem; }
        .device-item {
            padding: 0.75rem 1rem; background: var(--bg); border: 2px solid var(--border);
            border-radius: 8px; cursor: pointer; transition: all 0.2s;
            display: flex; align-items: center; gap: 0.75rem;
        }
        .device-item:hover { border-color: var(--accent); }
        .device-item.selected { border-color: var(--success); background: rgba(16, 185, 129, 0.08); }
        .device-item.selected::before { content: '✅'; }
        .device-name { font-size: 0.88rem; font-weight: 600; }
        .device-id { font-size: 0.7rem; color: var(--muted); font-family: monospace; }

        /* Level meter */
        .level-container { margin-top: 1rem; }
        .level-bar-bg {
            height: 20px; background: var(--bg); border-radius: 10px;
            overflow: hidden; border: 1px solid var(--border);
        }
        .level-bar {
            height: 100%; width: 0%; border-radius: 10px;
            background: linear-gradient(90deg, var(--success), var(--warning), var(--danger));
            transition: width 0.05s;
        }
        .level-label { font-size: 0.78rem; color: var(--text2); margin-top: 0.4rem; display: flex; justify-content: space-between; }

        /* Buttons */
        .btn {
            font-family: inherit; font-size: 0.88rem; font-weight: 600;
            padding: 10px 20px; border-radius: 8px; border: none;
            cursor: pointer; transition: all 0.2s;
            display: inline-flex; align-items: center; gap: 0.4rem;
        }
        .btn-primary { background: var(--accent); color: #fff; }
        .btn-primary:hover { background: #5558e6; }
        .btn-danger { background: var(--danger); color: #fff; }
        .btn-success { background: var(--success); color: #fff; }
        .btn-ghost { background: var(--bg); color: var(--text); border: 1px solid var(--border); }
        .btn:disabled { opacity: 0.4; cursor: not-allowed; }

        .btn-row { display: flex; gap: 0.75rem; flex-wrap: wrap; margin-top: 1rem; }

        /* Results */
        .result-box {
            margin-top: 1rem; padding: 1rem; background: var(--bg);
            border-radius: 8px; border-left: 3px solid var(--accent);
        }
        .result-box.error { border-left-color: var(--danger); }
        .result-box.success { border-left-color: var(--success); }
        .result-text { font-size: 0.92rem; line-height: 1.5; }
        .result-label { font-size: 0.72rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 0.3rem; }

        /* Status */
        .status { font-size: 0.85rem; color: var(--text2); margin-top: 0.75rem; }
        .status.recording { color: var(--danger); font-weight: 600; }
        .status.ok { color: var(--success); }

        audio { width: 100%; margin-top: 0.75rem; border-radius: 8px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🎙️ Microphone Test & Debug</h1>
        <a href="/">← Back to Recordings</a>
    </div>

    <div class="container">
        <!-- Step 1: Select Device -->
        <div class="section">
            <h2>📋 Step 1: Select Your Microphone</h2>
            <p style="font-size:0.82rem; color:var(--text2); margin-bottom:1rem;">
                Choose the correct mic input. If you see "Stereo Mix" selected, that's your problem —
                it captures system audio instead of your voice!
            </p>
            <div class="device-list" id="device-list">
                <div style="color:var(--muted)">Loading devices…</div>
            </div>
            <div class="btn-row">
                <button class="btn btn-ghost" onclick="refreshDevices()">🔄 Refresh Devices</button>
            </div>
        </div>

        <!-- Step 2: Live Level -->
        <div class="section">
            <h2>📊 Step 2: Check Audio Levels</h2>
            <p style="font-size:0.82rem; color:var(--text2); margin-bottom:0.75rem;">
                Speak into your mic — the bar should move. If it stays flat, you have the wrong device selected.
            </p>
            <div class="level-container">
                <div class="level-bar-bg">
                    <div class="level-bar" id="level-bar"></div>
                </div>
                <div class="level-label">
                    <span>Silent</span>
                    <span id="level-value">0%</span>
                    <span>Loud</span>
                </div>
            </div>
            <div class="btn-row">
                <button class="btn btn-primary" id="btn-monitor" onclick="toggleMonitor()">🎧 Start Monitoring</button>
            </div>
            <div class="status" id="monitor-status"></div>
        </div>

        <!-- Step 3: Record & Playback -->
        <div class="section">
            <h2>🔴 Step 3: Record & Playback Test</h2>
            <p style="font-size:0.82rem; color:var(--text2); margin-bottom:0.75rem;">
                Record yourself saying "Hello, testing one two three" — then play it back.
                If you hear YOUR voice, the mic is correct!
            </p>
            <div class="btn-row">
                <button class="btn btn-danger" id="btn-record" onclick="toggleTestRecord()">🔴 Record Test (5 sec)</button>
                <button class="btn btn-success" id="btn-transcribe" onclick="transcribeTest()" disabled>🔤 Transcribe with ElevenLabs</button>
            </div>
            <div class="status" id="record-status"></div>
            <div id="playback-area"></div>
            <div id="transcript-result"></div>
        </div>

        <!-- Step 4: Save & Use -->
        <div class="section">
            <h2>✅ Step 4: Save & Use in Interview</h2>
            <p style="font-size:0.82rem; color:var(--text2); margin-bottom:0.75rem;">
                Once you've confirmed the right microphone, click below to use it in interviews.
            </p>
            <div class="btn-row">
                <button class="btn btn-success" id="btn-save" onclick="savePreferredDevice()">💾 Use This Mic for Interviews</button>
            </div>
            <div class="status" id="save-status"></div>
        </div>
    </div>

    <script>
        let selectedDeviceId = null;
        let monitorStream = null;
        let monitorCtx = null;
        let monitorAnalyser = null;
        let isMonitoring = false;
        let testRecorder = null;
        let testBlob = null;

        // ── Device enumeration ──────────────────────────
        async function refreshDevices() {
            // Need to get permission first
            try {
                const tempStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                tempStream.getTracks().forEach(t => t.stop());
            } catch(e) {}

            const devices = await navigator.mediaDevices.enumerateDevices();
            const audioInputs = devices.filter(d => d.kind === 'audioinput');

            const list = document.getElementById('device-list');

            if (audioInputs.length === 0) {
                list.innerHTML = '<div style="color:var(--danger)">❌ No microphones found!</div>';
                return;
            }

            list.innerHTML = audioInputs.map((d, i) => {
                const name = d.label || `Microphone ${i + 1}`;
                const isStereoMix = name.toLowerCase().includes('stereo mix') || name.toLowerCase().includes('what u hear');
                return `
                    <div class="device-item ${d.deviceId === selectedDeviceId ? 'selected' : ''}"
                         onclick="selectDevice('${d.deviceId}', this)"
                         style="${isStereoMix ? 'border-color: var(--danger); background: rgba(239,68,68,0.08);' : ''}">
                        <div>
                            <div class="device-name">
                                ${isStereoMix ? '⚠️ ' : '🎤 '}${name}
                                ${isStereoMix ? ' <span style="color:var(--danger);font-size:0.72rem;">(DO NOT USE — captures system audio!)</span>' : ''}
                            </div>
                            <div class="device-id">${d.deviceId.substring(0, 20)}…</div>
                        </div>
                    </div>
                `;
            }).join('');
        }

        function selectDevice(deviceId, el) {
            selectedDeviceId = deviceId;
            document.querySelectorAll('.device-item').forEach(d => d.classList.remove('selected'));
            el.classList.add('selected');

            // Restart monitor if active
            if (isMonitoring) { stopMonitor(); startMonitor(); }
        }

        // ── Audio Level Monitor ─────────────────────────
        async function toggleMonitor() {
            isMonitoring ? stopMonitor() : startMonitor();
        }

        async function startMonitor() {
            const constraints = { audio: selectedDeviceId
                ? { deviceId: { exact: selectedDeviceId }, echoCancellation: true, noiseSuppression: true }
                : { echoCancellation: true, noiseSuppression: true }
            };

            try {
                monitorStream = await navigator.mediaDevices.getUserMedia(constraints);
            } catch(e) {
                document.getElementById('monitor-status').textContent = '❌ Cannot access mic: ' + e.message;
                return;
            }

            monitorCtx = new AudioContext();
            const source = monitorCtx.createMediaStreamSource(monitorStream);
            monitorAnalyser = monitorCtx.createAnalyser();
            monitorAnalyser.fftSize = 256;
            source.connect(monitorAnalyser);

            isMonitoring = true;
            document.getElementById('btn-monitor').textContent = '⏹ Stop Monitoring';
            document.getElementById('btn-monitor').className = 'btn btn-danger';
            document.getElementById('monitor-status').textContent = '🎧 Speak now — watch the level bar move';
            document.getElementById('monitor-status').className = 'status recording';

            updateLevel();
        }

        function updateLevel() {
            if (!isMonitoring || !monitorAnalyser) return;

            const data = new Uint8Array(monitorAnalyser.frequencyBinCount);
            monitorAnalyser.getByteFrequencyData(data);
            const avg = data.reduce((a, b) => a + b, 0) / data.length;
            const pct = Math.min(100, Math.round(avg / 128 * 100));

            document.getElementById('level-bar').style.width = pct + '%';
            document.getElementById('level-value').textContent = pct + '%';

            requestAnimationFrame(updateLevel);
        }

        function stopMonitor() {
            isMonitoring = false;
            if (monitorStream) { monitorStream.getTracks().forEach(t => t.stop()); monitorStream = null; }
            if (monitorCtx) { monitorCtx.close(); monitorCtx = null; }

            document.getElementById('btn-monitor').textContent = '🎧 Start Monitoring';
            document.getElementById('btn-monitor').className = 'btn btn-primary';
            document.getElementById('monitor-status').textContent = '';
            document.getElementById('monitor-status').className = 'status';
            document.getElementById('level-bar').style.width = '0%';
            document.getElementById('level-value').textContent = '0%';
        }

        // ── Test Record ─────────────────────────────────
        async function toggleTestRecord() {
            if (testRecorder && testRecorder.state === 'recording') {
                testRecorder.stop();
                return;
            }

            const constraints = { audio: selectedDeviceId
                ? { deviceId: { exact: selectedDeviceId }, echoCancellation: true, noiseSuppression: true, autoGainControl: true }
                : { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
            };

            let stream;
            try {
                stream = await navigator.mediaDevices.getUserMedia(constraints);
            } catch(e) {
                document.getElementById('record-status').textContent = '❌ ' + e.message;
                return;
            }

            const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
                ? 'audio/webm;codecs=opus' : 'audio/webm';

            const chunks = [];
            testRecorder = new MediaRecorder(stream, { mimeType: mime });
            testRecorder.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };

            testRecorder.onstop = () => {
                stream.getTracks().forEach(t => t.stop());
                testBlob = new Blob(chunks, { type: mime });

                document.getElementById('btn-record').textContent = '🔴 Record Test (5 sec)';
                document.getElementById('record-status').textContent = `✅ Recorded ${(testBlob.size / 1024).toFixed(1)} KB`;
                document.getElementById('record-status').className = 'status ok';
                document.getElementById('btn-transcribe').disabled = false;

                // Playback
                const url = URL.createObjectURL(testBlob);
                document.getElementById('playback-area').innerHTML =
                    `<audio controls src="${url}"></audio>
                     <p style="font-size:0.78rem; color:var(--text2); margin-top:0.3rem;">
                     ▶️ Play this — do you hear YOUR voice or system audio?</p>`;
            };

            testRecorder.start(250);
            document.getElementById('btn-record').textContent = '⏹ Stop Recording';
            document.getElementById('record-status').textContent = '🔴 Recording… speak now!';
            document.getElementById('record-status').className = 'status recording';

            // Auto-stop after 5 seconds
            setTimeout(() => {
                if (testRecorder && testRecorder.state === 'recording') testRecorder.stop();
            }, 5000);
        }

        // ── Transcribe Test ─────────────────────────────
        async function transcribeTest() {
            if (!testBlob) return;

            document.getElementById('transcript-result').innerHTML =
                '<div class="result-box"><div class="result-label">Transcribing…</div><div class="result-text">⏳ Sending to ElevenLabs…</div></div>';

            try {
                const fd = new FormData();
                fd.append('audio', testBlob, 'test-recording.webm');
                fd.append('session_id', 'mic-test');

                const res = await fetch('/api/stt/transcribe', { method: 'POST', body: fd });
                const data = await res.json();
                const text = (data.transcript || '').trim();

                document.getElementById('transcript-result').innerHTML = text
                    ? `<div class="result-box success">
                        <div class="result-label">✅ ElevenLabs Transcript</div>
                        <div class="result-text" style="font-size:1.1rem; font-weight:600;">"${text}"</div>
                       </div>`
                    : `<div class="result-box error">
                        <div class="result-label">⚠️ No transcript returned</div>
                        <div class="result-text">ElevenLabs couldn't detect speech. Try speaking louder or selecting a different mic.</div>
                       </div>`;
            } catch(e) {
                document.getElementById('transcript-result').innerHTML =
                    `<div class="result-box error">
                        <div class="result-label">❌ Error</div>
                        <div class="result-text">${e.message}</div>
                     </div>`;
            }
        }

        // ── Save preferred device ───────────────────────
        async function savePreferredDevice() {
            if (!selectedDeviceId) {
                document.getElementById('save-status').textContent = '⚠️ Select a device first!';
                return;
            }

            try {
                // Save to server
                await fetch('/api/preferred-device', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ device_id: selectedDeviceId })
                });

                // Also save to localStorage for the interview page
                localStorage.setItem('preferredMicDeviceId', selectedDeviceId);

                document.getElementById('save-status').textContent = '✅ Saved! This mic will be used for interviews.';
                document.getElementById('save-status').className = 'status ok';
            } catch(e) {
                document.getElementById('save-status').textContent = '❌ ' + e.message;
            }
        }

        // Init
        refreshDevices();
    </script>
</body>
</html>
"""


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print(f"[STT Server] Starting on port {PORT}...")
    print(f"[STT Server] ElevenLabs Scribe v1 ready")
    print(f"[STT Server] Transcribe: http://localhost:{PORT}/api/stt/transcribe")
    print(f"[STT Server] Audio Player: http://localhost:{PORT}/")
    print(f"[STT Server] Mic Test: http://localhost:{PORT}/mic-test")
    app.run(host="0.0.0.0", port=PORT, debug=True)
