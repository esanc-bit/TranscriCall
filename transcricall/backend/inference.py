import os
import io
import wave
import shutil
import zipfile
from typing import Tuple, Dict


# Base directory of the project (one level up from this file).  Using a
# relative path avoids hard-coding ``/workspace/transcricall`` which breaks when
# the repository directory has a different name or casing.
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class Transcriber:
    def __init__(self, engine: str = "vosk", language: str = "es", model_path: str = ""):
        self.engine = engine
        self.language = language
        self.model_path = model_path or default_model_path(engine, language)
        if engine == "vosk":
            try:
                from vosk import Model, KaldiRecognizer
            except Exception as e:
                raise RuntimeError("Vosk not installed. Please `pip install vosk`." ) from e
            if not os.path.isdir(self.model_path):
                raise RuntimeError(f"Vosk model not found at {self.model_path}")
            self._vosk_model = Model(self.model_path)
        else:
            raise RuntimeError(f"Unsupported engine: {engine}")

    def transcribe_chunk(self, wav_bytes: bytes) -> Tuple[str, Dict[str, int]]:
        if self.engine == "vosk":
            return self._transcribe_vosk(wav_bytes)
        raise RuntimeError("No engine available")

    def _transcribe_vosk(self, wav_bytes: bytes) -> Tuple[str, Dict[str, int]]:
        from vosk import KaldiRecognizer
        import json

        with io.BytesIO(wav_bytes) as bio:
            with wave.open(bio, 'rb') as wf:
                if wf.getnchannels() != 1 or wf.getsampwidth() != 2:
                    raise ValueError("Audio must be mono PCM16. Use the capture client provided.")
                sample_rate = wf.getframerate()
                if sample_rate != 16000:
                    # Vosk works with any SR, but accuracy is best at 16k; continue anyway
                    pass
                rec = KaldiRecognizer(self._vosk_model, sample_rate)
                rec.SetWords(True)
                # Feed all at once since this is a short chunk
                data = wf.readframes(wf.getnframes())
                rec.AcceptWaveform(data)
                result = json.loads(rec.Result())
                text = result.get("text", "").strip()
                words = result.get("result", [])
                start_ms = int(words[0]["start"] * 1000) if words else 0
                end_ms = int(words[-1]["end"] * 1000) if words else 0
                return text, {"start_ms": start_ms, "end_ms": end_ms}


def ensure_default_model(engine: str, language: str, model_path: str = ""):
    if engine != "vosk":
        return
    path = model_path or default_model_path(engine, language)
    if os.path.isdir(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Minimal bootstrap: try to fetch small ES model automatically if env ALLOW_AUTO_DOWNLOAD=1
    if os.getenv("ALLOW_AUTO_DOWNLOAD", "0") != "1":
        return
    # URLs from alphacephei Vosk models
    urls = {
        "es": (
            "https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip",
            "vosk-model-small-es-0.42",
        ),
        "en": (
            "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
            "vosk-model-small-en-us-0.15",
        ),
    }
    if language not in urls:
        return
    url, folder_name = urls[language]
    tmp_zip = path + ".zip"
    try:
        import urllib.request
        urllib.request.urlretrieve(url, tmp_zip)
        with zipfile.ZipFile(tmp_zip, 'r') as zf:
            zf.extractall(os.path.dirname(path))
        src = os.path.join(os.path.dirname(path), folder_name)
        if os.path.isdir(src):
            shutil.move(src, path)
    finally:
        if os.path.exists(tmp_zip):
            os.remove(tmp_zip)


def default_model_path(engine: str, language: str) -> str:
    """Return the default directory where models are stored.

    The previous implementation hardcoded ``/workspace/transcricall`` which
    fails if the repository lives elsewhere or uses a different name.  By
    basing the path on ``BASE_DIR`` we make it portable.
    """

    base = os.path.join(BASE_DIR, "models")
    if engine == "vosk":
        sub = {
            "es": "vosk-model-small-es",
            "en": "vosk-model-small-en",
        }.get(language, f"vosk-model-small-{language}")
        return os.path.join(base, sub)
    return os.path.join(base, f"{engine}-{language}")