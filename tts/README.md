# 🔊 TTS — Open Source High-Quality Text-to-Speech Module

This module integrates **Coqui TTS** (formerly Mozilla TTS), one of the best open-source, neural TTS engines, into the RooterF project.

---

## 📁 Folder Structure

```
tts/
├── models/            → Downloaded TTS model weights (.pth, config.json)
├── audio_output/      → Generated .wav / .mp3 audio files
├── scripts/           → Python backend scripts for TTS processing
│   ├── tts_engine.py  → Core TTS engine wrapper
│   └── api.py         → Flask REST API for TTS
├── static/
│   ├── js/tts.js      → Frontend JavaScript client
│   └── css/tts.css    → Styling for TTS UI widget
├── templates/
│   └── tts_demo.html  → Standalone demo page
└── requirements.txt   → Python dependencies
```

---

## 🚀 Recommended Open-Source TTS Engines

| Engine | Quality | Language | Speed | Notes |
|---|---|---|---|---|
| **Coqui TTS** ⭐ | ★★★★★ | Multi | Fast | Best overall, VITS model |
| **Silero TTS** | ★★★★☆ | Multi | Very Fast | Lightweight, great for production |
| **edge-tts** | ★★★★★ | Multi | Instant | Uses Microsoft Edge neural voices (free) |
| **pyttsx3** | ★★☆☆☆ | EN | Fast | Offline, basic quality |
| **Bark** | ★★★★★ | Multi | Slow | Emotion & music, GPU recommended |

> **Recommended**: `edge-tts` for instant high-quality output, or `Coqui TTS` with VITS model for fully offline use.

---

## ⚙️ Quick Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Run the TTS API server
python scripts/api.py

# Or use CLI
python scripts/tts_engine.py --text "Hello World" --out audio_output/hello.wav
```

---

## 🌐 API Endpoint

```
POST /api/tts/speak
Content-Type: application/json

{
  "text": "Hello, this is a test.",
  "voice": "en-US-JennyNeural",
  "speed": 1.0
}

Response: audio/wav stream
```

---

## 📦 Dependencies

See `requirements.txt` for the full list.
