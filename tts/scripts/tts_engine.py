"""
tts_engine.py — Core TTS Engine Wrapper
Supports: edge-tts (online, best quality) and Coqui TTS (offline, neural)
"""

import asyncio
import os
import argparse
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────
OUTPUT_DIR = Path(__file__).parent.parent / "audio_output"
OUTPUT_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────────
# ENGINE 1: edge-tts (High Quality, Online)
# Uses Microsoft Edge Neural Voices — Free
# ─────────────────────────────────────────────
async def speak_edge_tts(text: str, voice: str = "en-US-JennyNeural",
                          speed: float = 1.0, output_file: str = None) -> str:
    """
    Generate speech using edge-tts (Microsoft neural voices).
    Returns path to the output .mp3 file.
    """
    try:
        import edge_tts

        rate_str = f"+{int((speed - 1) * 100)}%" if speed >= 1 else f"{int((speed - 1) * 100)}%"
        communicate = edge_tts.Communicate(text, voice, rate=rate_str)

        if not output_file:
            output_file = str(OUTPUT_DIR / "output_edge.mp3")

        await communicate.save(output_file)
        print(f"[edge-tts] ✅ Audio saved → {output_file}")
        return output_file

    except ImportError:
        print("[edge-tts] ❌ Not installed. Run: pip install edge-tts")
        return None
    except Exception as e:
        print(f"[edge-tts] ❌ Error: {e}")
        return None


def edge_tts_speak(text: str, voice: str = "en-US-JennyNeural",
                   speed: float = 1.0, output_file: str = None) -> str:
    """Sync wrapper for edge-tts."""
    return asyncio.run(speak_edge_tts(text, voice, speed, output_file))


# ─────────────────────────────────────────────
# ENGINE 2: Silero TTS (Offline, Fast, Good Quality)
# ─────────────────────────────────────────────
def silero_tts_speak(text: str, model_id: str = "en_0", output_file: str = None) -> str:
    """
    Generate speech using Silero TTS (offline, fast).
    Requires: pip install silero
    """
    try:
        import torch
        import soundfile as sf

        device = torch.device("cpu")
        model, _ = torch.hub.load(
            repo_or_dir="snakers4/silero-models",
            model="silero_tts",
            language="en",
            speaker="v3_en",
        )
        model.to(device)

        audio = model.apply_tts(text=text, speaker=model_id, sample_rate=48000)

        if not output_file:
            output_file = str(OUTPUT_DIR / "output_silero.wav")

        sf.write(output_file, audio.numpy(), 48000)
        print(f"[Silero] ✅ Audio saved → {output_file}")
        return output_file

    except ImportError:
        print("[Silero] ❌ Not installed. Run: pip install torch soundfile")
        return None
    except Exception as e:
        print(f"[Silero] ❌ Error: {e}")
        return None


# ─────────────────────────────────────────────
# ENGINE 3: Coqui TTS (Offline, Neural, Best Offline Quality)
# ─────────────────────────────────────────────
def coqui_tts_speak(text: str, model_name: str = "tts_models/en/ljspeech/vits",
                    output_file: str = None) -> str:
    """
    Generate speech using Coqui TTS with VITS model (offline, neural).
    Requires: pip install coqui-tts
    """
    try:
        from TTS.api import TTS

        if not output_file:
            output_file = str(OUTPUT_DIR / "output_coqui.wav")

        tts = TTS(model_name=model_name, progress_bar=False)
        tts.tts_to_file(text=text, file_path=output_file)
        print(f"[Coqui] ✅ Audio saved → {output_file}")
        return output_file

    except ImportError:
        print("[Coqui] ❌ Not installed. Run: pip install coqui-tts")
        return None
    except Exception as e:
        print(f"[Coqui] ❌ Error: {e}")
        return None


# ─────────────────────────────────────────────
# UNIFIED SPEAK FUNCTION
# ─────────────────────────────────────────────
def speak(text: str, engine: str = "edge", voice: str = "en-US-JennyNeural",
          speed: float = 1.0, output_file: str = None) -> str:
    """
    Unified TTS function. Choose engine: 'edge', 'silero', or 'coqui'
    """
    print(f"[TTS] Speaking with [{engine}] engine: \"{text[:60]}...\"" if len(text) > 60 else f"[TTS] Speaking: \"{text}\"")

    if engine == "edge":
        return edge_tts_speak(text, voice, speed, output_file)
    elif engine == "silero":
        return silero_tts_speak(text, output_file=output_file)
    elif engine == "coqui":
        return coqui_tts_speak(text, output_file=output_file)
    else:
        print(f"[TTS] ❌ Unknown engine: {engine}. Use 'edge', 'silero', or 'coqui'.")
        return None


# ─────────────────────────────────────────────
# AVAILABLE EDGE-TTS VOICES
# ─────────────────────────────────────────────
EDGE_TTS_VOICES = {
    "English (US) Female": "en-US-JennyNeural",
    "English (US) Male": "en-US-GuyNeural",
    "English (UK) Female": "en-GB-SoniaNeural",
    "English (UK) Male": "en-GB-RyanNeural",
    "English (AU) Female": "en-AU-NatashaNeural",
    "Hindi Female": "hi-IN-SwaraNeural",
    "Hindi Male": "hi-IN-MadhurNeural",
    "French Female": "fr-FR-DeniseNeural",
    "German Female": "de-DE-KatjaNeural",
    "Spanish Female": "es-ES-ElviraNeural",
    "Japanese Female": "ja-JP-NanamiNeural",
    "Chinese Female": "zh-CN-XiaoxiaoNeural",
    "Arabic Female": "ar-SA-ZariyahNeural",
}


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Open Source High-Quality TTS Engine")
    parser.add_argument("--text", type=str, required=True, help="Text to convert to speech")
    parser.add_argument("--engine", type=str, default="edge", choices=["edge", "silero", "coqui"],
                        help="TTS engine to use (default: edge)")
    parser.add_argument("--voice", type=str, default="en-US-JennyNeural", help="Voice name (edge-tts only)")
    parser.add_argument("--speed", type=float, default=1.0, help="Speech speed multiplier (default: 1.0)")
    parser.add_argument("--out", type=str, default=None, help="Output file path")
    args = parser.parse_args()

    result = speak(args.text, engine=args.engine, voice=args.voice,
                   speed=args.speed, output_file=args.out)
    if result:
        print(f"\n✅ Done! File: {result}")
