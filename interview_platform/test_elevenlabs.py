import os
import tempfile
from pydub import AudioSegment

# Let's create a quick test audio snippet and transcribe it via elevenlabs
import requests

ELEVENLABS_API_KEY = "sk_731f5124d148dce5da10b34d8789430a32317b8f5dbccdb7"

url = "https://api.elevenlabs.io/v1/speech-to-text"
headers = {
    "xi-api-key": ELEVENLABS_API_KEY
}

# we don't have an audio file here immediately but we can generate 1 second of silence to test auth.
with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
    f.write(b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00')
    test_file = f.name

with open(test_file, 'rb') as audio_f:
    files = {
        'file': (test_file, audio_f, 'audio/wav')
    }
    data = {"model_id": "scribe_v1"}
    response = requests.post(url, headers=headers, data=data, files=files)

print("Status:", response.status_code)
print("Response:", response.text)
os.unlink(test_file)
