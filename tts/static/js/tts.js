/**
 * tts.js — Frontend TTS Client
 * Connects to the TTS Flask API and plays audio in the browser.
 */

class TTSClient {
    constructor(apiBase = "http://localhost:5050") {
        this.apiBase = apiBase;
        this.currentAudio = null;
        this.isPlaying = false;
    }

    /**
     * Convert text to speech and play it in the browser.
     * @param {string} text - Text to speak
     * @param {string} voice - Edge-TTS voice name
     * @param {number} speed - Playback speed (0.5 - 2.0)
     * @param {string} engine - TTS engine: "edge", "silero", "coqui"
     */
    async speak(text, voice = "en-US-JennyNeural", speed = 1.0, engine = "edge") {
        if (!text || !text.trim()) return;

        // Stop any current audio
        this.stop();

        try {
            const response = await fetch(`${this.apiBase}/api/tts/speak`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text, voice, speed, engine }),
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.error || "TTS request failed");
            }

            const blob = await response.blob();
            const url = URL.createObjectURL(blob);

            this.currentAudio = new Audio(url);
            this.currentAudio.playbackRate = speed;
            this.isPlaying = true;

            this.currentAudio.onended = () => {
                this.isPlaying = false;
                URL.revokeObjectURL(url);
                this._onEnd();
            };

            await this.currentAudio.play();
            this._onStart();

        } catch (error) {
            console.error("[TTS] Error:", error.message);
            this._onError(error);
        }
    }

    /** Stop current audio playback. */
    stop() {
        if (this.currentAudio) {
            this.currentAudio.pause();
            this.currentAudio.currentTime = 0;
            this.currentAudio = null;
            this.isPlaying = false;
            this._onStop();
        }
    }

    /** Load available voices from the API. */
    async getVoices() {
        const res = await fetch(`${this.apiBase}/api/tts/voices`);
        return await res.json();
    }

    // Event hooks (override these)
    _onStart() {}
    _onEnd() {}
    _onStop() {}
    _onError(err) {}
}

// ─────────────────────────────────────────────
// TTS Widget — Auto-init on DOM ready
// ─────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
    const client = new TTSClient();

    const speakBtn = document.getElementById("tts-speak-btn");
    const stopBtn = document.getElementById("tts-stop-btn");
    const textInput = document.getElementById("tts-text-input");
    const voiceSelect = document.getElementById("tts-voice-select");
    const speedInput = document.getElementById("tts-speed-input");
    const statusEl = document.getElementById("tts-status");

    function setStatus(msg, type = "info") {
        if (!statusEl) return;
        statusEl.textContent = msg;
        statusEl.className = `tts-status tts-status--${type}`;
    }

    client._onStart = () => setStatus("🔊 Speaking...", "playing");
    client._onEnd = () => setStatus("✅ Done!", "done");
    client._onStop = () => setStatus("⏹ Stopped", "idle");
    client._onError = (e) => setStatus(`❌ ${e.message}`, "error");

    if (speakBtn) {
        speakBtn.addEventListener("click", async () => {
            const text = textInput?.value || "";
            const voice = voiceSelect?.value || "en-US-JennyNeural";
            const speed = parseFloat(speedInput?.value || "1.0");
            setStatus("⏳ Generating audio...", "loading");
            await client.speak(text, voice, speed);
        });
    }

    if (stopBtn) {
        stopBtn.addEventListener("click", () => client.stop());
    }

    // Load voices into select
    if (voiceSelect) {
        client.getVoices().then((data) => {
            const voices = data.edge_tts || {};
            Object.entries(voices).forEach(([label, value]) => {
                const opt = document.createElement("option");
                opt.value = value;
                opt.textContent = label;
                if (value === "en-US-JennyNeural") opt.selected = true;
                voiceSelect.appendChild(opt);
            });
        });
    }

    // Expose globally
    window.TTS = client;
});
