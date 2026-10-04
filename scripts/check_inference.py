"""Exercise the full API with real models and a supplied image (no test doubles)."""
import argparse
import io
import json
import sys
import tempfile
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from nexa_mind import create_app
from nexa_mind.services.vision import VisionService


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--question", default="What animals are in the picture?")
    parser.add_argument("--expected-label")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    if args.offline:
        import os
        os.environ["HF_HUB_OFFLINE"] = "1"
    service = VisionService(PROJECT / "instance" / "models")
    service.wait_ready()
    with tempfile.TemporaryDirectory(prefix="nexa-inference-") as directory:
        app = create_app({"TESTING": True, "DATA_DIR": directory, "VISION_SERVICE": service})
        client = app.test_client()
        client.get("/")
        with client.session_transaction() as session:
            headers = {"X-CSRF-Token": session["csrf"]}
        started = time.perf_counter()
        response = client.post("/api/analyses", headers=headers, data={"image": (io.BytesIO(args.image.read_bytes()), args.image.name)})
        assert response.status_code == 201, response.json
        detection_seconds = time.perf_counter() - started
        analysis = response.json
        if args.expected_label:
            assert any(item["label"] == args.expected_label for item in analysis["detections"]), analysis["detections"]
        started = time.perf_counter()
        answer = client.post(f"/api/analyses/{analysis['id']}/questions", headers=headers, json={"question": args.question})
        assert answer.status_code == 201, answer.json
        question_seconds = time.perf_counter() - started
        assert answer.json["result"]["answer"]
        exported = client.get(f"/api/analyses/{analysis['id']}/export").json
        assert len(exported["questions"]) == 1
        assert client.delete(f"/api/analyses/{analysis['id']}", headers=headers).status_code == 204
        assert client.get(f"/api/analyses/{analysis['id']}").status_code == 404
        print(json.dumps({"models": service.status(), "detections": analysis["detections"], "question": args.question,
                          "result": answer.json["result"], "detection_seconds": round(detection_seconds, 3),
                          "question_seconds": round(question_seconds, 3), "export_and_delete": "passed"}, indent=2))


if __name__ == "__main__":
    main()
