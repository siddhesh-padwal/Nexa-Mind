"""Prefetch the pinned conversation and English speech models."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

from huggingface_hub import snapshot_download
from nexa_mind.services.conversation import CHAT_MODEL, CHAT_REVISION, SPEECH_MODEL, SPEECH_REVISION

if __name__ == "__main__":
    root = Path(os.environ.get("NEXA_DATA_DIR", ROOT / "instance")) / "models"
    for repo, revision, folder in [(CHAT_MODEL, CHAT_REVISION, "conversation"), (SPEECH_MODEL, SPEECH_REVISION, "speech")]:
        target = root / folder
        print(f"Downloading {repo}…", flush=True)
        snapshot_download(repo, revision=revision, local_dir=str(target),
                          allow_patterns=["*.json", "*.safetensors", "*.txt", "model.bin"], max_workers=3)
        (target / ".ready").touch()
        print(f"Saved {repo}", flush=True)
