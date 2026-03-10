import torch
from transformers import AutoModelForSpeechSeq2Seq, PreTrainedTokenizerFast, AutoConfig
import torchaudio

try:
    print("Loading model...")
    model = AutoModelForSpeechSeq2Seq.from_pretrained("usefulsensors/moonshine-tiny", trust_remote_code=True)
    tokenizer = PreTrainedTokenizerFast.from_pretrained("usefulsensors/moonshine-tiny")
    print("Model loaded successfully!")
except Exception as e:
    print("Error:", e)
