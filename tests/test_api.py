import io
import json

import pytest
from PIL import Image

from nexa_mind import create_app
from nexa_mind.services.vision import ModelBusy, ModelUnavailable, VisionService
from nexa_mind.storage import db


def photo(mode="RGB", size=(100, 60), format="PNG"):
    stream = io.BytesIO()
    Image.new(mode, size, "red").save(stream, format)
    stream.seek(0)
    return stream


def upload(client, csrf, filename="photo.png", stream=None):
    return client.post("/api/analyses", headers=csrf, data={"image": (stream or photo(), filename)})


def test_complete_persistent_lifecycle(app, client, csrf):
    response = upload(client, csrf)
    assert response.status_code == 201
    analysis = response.json
    analysis_id = analysis["id"]
    assert analysis["width"] == 100
    assert client.get(analysis["image_url"]).mimetype == "image/jpeg"
    question = client.post(f"/api/analyses/{analysis_id}/questions", headers=csrf, json={"question": "What color is it?"})
    assert question.status_code == 201
    assert question.json["result"]["short_answer"] == "fixture-answer"
    assert len(question.json["result"]["answer"]) >= 100
    second_app = create_app({"TESTING": True, "DATA_DIR": app.config["DATA_DIR"], "SECRET_KEY": "test-secret", "VISION_SERVICE": app.extensions["vision"]})
    saved = second_app.test_client().get(f"/api/analyses/{analysis_id}").json
    assert saved["questions"][0]["question"] == "What color is it?"
    export = client.get(f"/api/analyses/{analysis_id}/export")
    assert export.status_code == 200
    assert "attachment" in export.headers["Content-Disposition"]
    assert export.json["questions"][0]["result"]["short_answer"] == "fixture-answer"
    assert client.delete(f"/api/analyses/{analysis_id}", headers=csrf).status_code == 204
    assert client.get(f"/api/analyses/{analysis_id}").status_code == 404
    assert not list((app.config["DATA_DIR"] / "uploads").iterdir())
    with app.app_context():
        assert db().execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 0


@pytest.mark.parametrize("body", [{}, {"question": "  "}, {"question": 5}, {"question": "x" * 301}, [], None])
def test_invalid_questions(client, csrf, body):
    analysis_id = upload(client, csrf).json["id"]
    response = client.post(f"/api/analyses/{analysis_id}/questions", headers=csrf, json=body)
    assert response.status_code == 400


def test_csrf_and_host_protection(client):
    assert client.post("/api/models/load").status_code == 403
    assert client.delete("/api/analyses/missing").status_code == 403
    assert client.get("/", headers={"Host": "attacker.example"}).status_code == 400


def test_security_headers_and_no_external_assets(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert b"https://" not in response.data


@pytest.mark.parametrize("data,name", [(b"not an image", "photo.png"), (b"<svg/>", "image.svg"), (b"", "empty.jpg")])
def test_invalid_images(client, csrf, data, name):
    response = upload(client, csrf, name, io.BytesIO(data))
    assert response.status_code == 400
    assert client.get("/api/analyses").json["analyses"] == []


def test_image_limits_and_normalization(client, csrf):
    assert upload(client, csrf, stream=io.BytesIO(b"x" * (8 * 1024 * 1024 + 1))).status_code == 400
    assert upload(client, csrf, stream=io.BytesIO(b"x" * (10 * 1024 * 1024))).status_code == 413
    assert upload(client, csrf, stream=photo(size=(5000, 4100))).status_code == 400
    normalized = upload(client, csrf, stream=photo(mode="RGBA", size=(2000, 1000))).json
    assert (normalized["width"], normalized["height"]) == (1600, 800)


def test_exif_orientation_and_metadata_stripping(client, csrf):
    source = Image.new("RGB", (80, 40), "blue")
    exif = source.getexif(); exif[274] = 6; exif[270] = "private metadata"
    stream = io.BytesIO(); source.save(stream, "JPEG", exif=exif); stream.seek(0)
    result = upload(client, csrf, "rotated.jpg", stream).json
    assert (result["width"], result["height"]) == (40, 80)
    with Image.open(io.BytesIO(client.get(result["image_url"]).data)) as saved:
        assert not saved.getexif()


def test_filename_and_query_safety(client, csrf):
    result = upload(client, csrf, "../../<script>alert.png").json
    assert "/" not in result["name"] and "<" not in result["name"]
    assert client.get("/api/analyses/' OR 1=1 --").status_code == 404
    assert client.get("/api/analyses/missing/image").status_code == 404


def test_unavailable_and_busy_never_create_fake_results(app, client, csrf):
    for error in [ModelUnavailable("Not ready"), ModelBusy("Busy")]:
        def fail(image):
            raise error
        app.extensions["vision"].detect = fail
        response = upload(client, csrf)
        assert response.status_code == 503
        assert client.get("/api/analyses").json["analyses"] == []


def test_model_service_rejects_unloaded_inference(tmp_path):
    service = VisionService(tmp_path)
    with pytest.raises(ModelUnavailable):
        service.detect(Image.new("RGB", (20, 20)))


def test_model_status_and_load(client, csrf):
    assert client.get("/api/status").json["state"] == "ready"
    assert client.post("/api/models/load", headers=csrf).status_code == 202


def test_unsupported_and_animated_formats(client, csrf):
    assert upload(client, csrf, "still.gif", photo(format="GIF")).status_code == 400
    stream = io.BytesIO()
    Image.new("RGB", (30, 30), "red").save(stream, "WEBP", save_all=True, append_images=[Image.new("RGB", (30, 30), "blue")], duration=100, loop=0)
    stream.seek(0)
    assert upload(client, csrf, "animation.webp", stream).status_code == 400
