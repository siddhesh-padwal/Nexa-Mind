import json
import re
import secrets
import sqlite3
import uuid
from pathlib import Path

from flask import Blueprint, abort, current_app, jsonify, render_template, request, send_file, session
from PIL import Image
from werkzeug.utils import secure_filename

from . import storage
from .services.images import normalize_image
from .services.vision import ModelBusy, ModelUnavailable
from .services.knowledge import KnowledgeUnavailable, learning_topic

bp = Blueprint("main", __name__)


def vision():
    return current_app.extensions["vision"]


def get_analysis(analysis_id):
    row = storage.db().execute("SELECT * FROM analyses WHERE id=?", (analysis_id,)).fetchone()
    if row is None:
        abort(404, description="This analysis no longer exists.")
    return row


def image_path(analysis_id):
    # The ID is looked up in SQLite before constructing a path.
    row = get_analysis(analysis_id)
    return Path(current_app.config["DATA_DIR"]) / "uploads" / f"{row['id']}.jpg"


@bp.errorhandler(ModelUnavailable)
@bp.errorhandler(ModelBusy)
@bp.errorhandler(KnowledgeUnavailable)
def model_error(error):
    return jsonify(error=str(error)), 503


@bp.get("/")
def index():
    session.setdefault("csrf", secrets.token_urlsafe(32))
    return render_template("index.html", csrf_token=session["csrf"])


@bp.get("/api/status")
def status():
    result = vision().status()
    result["conversation"] = current_app.extensions["conversation"].status()
    return jsonify(result)


@bp.post("/api/models/load")
def load_models():
    vision().start()
    current_app.extensions["conversation"].start()
    return jsonify(vision().status()), 202


@bp.get("/api/analyses")
def list_analyses():
    rows = storage.db().execute("SELECT * FROM analyses ORDER BY created_at DESC LIMIT 100").fetchall()
    return jsonify(analyses=[storage.serialize(row, include_questions=False) for row in rows])


@bp.post("/api/analyses")
def create_analysis():
    upload = request.files.get("image")
    if upload is None or not upload.filename:
        return jsonify(error="Choose an image to analyze."), 400
    try:
        image = normalize_image(upload)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    detections = vision().detect(image)
    analysis_id = uuid.uuid4().hex
    path = Path(current_app.config["DATA_DIR"]) / "uploads" / f"{analysis_id}.jpg"
    name = (secure_filename(upload.filename) or "image.jpg")[:120]
    try:
        image.save(path, "JPEG", quality=93)
        with storage.db():
            storage.db().execute("INSERT INTO analyses VALUES(?,?,?,?,?,?)", (
                analysis_id, name, image.width, image.height, json.dumps(detections), storage.now(),
            ))
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return jsonify(storage.serialize(get_analysis(analysis_id))), 201


@bp.get("/api/analyses/<analysis_id>")
def retrieve_analysis(analysis_id):
    return jsonify(storage.serialize(get_analysis(analysis_id)))


@bp.get("/api/analyses/<analysis_id>/image")
def retrieve_image(analysis_id):
    path = image_path(analysis_id)
    if not path.is_file():
        abort(404, description="The saved image is missing from local storage.")
    return send_file(path, mimetype="image/jpeg")


@bp.post("/api/analyses/<analysis_id>/questions")
def answer_question(analysis_id):
    path = image_path(analysis_id)
    payload = request.get_json(silent=True)
    question = payload.get("question") if isinstance(payload, dict) else None
    if not isinstance(question, str) or not question.strip():
        return jsonify(error="Enter a question about this image."), 400
    question = question.strip()
    if len(question) > 300:
        return jsonify(error="Keep your question under 300 characters."), 400
    try:
        with Image.open(path) as source:
            result = vision().answer(source.convert("RGB"), question)
            result = expand_visual_answer(result, get_analysis(analysis_id))
    except FileNotFoundError:
        abort(404, description="The saved image is missing from local storage.")
    except ValueError as error:
        return jsonify(error=str(error)), 400
    created = storage.now()
    try:
        with storage.db():
            cursor = storage.db().execute("INSERT INTO questions(analysis_id,question,result,created_at) VALUES(?,?,?,?)",
                                          (analysis_id, question, json.dumps(result), created))
    except sqlite3.IntegrityError:
        abort(404, description="This analysis was deleted while the question was processing.")
    return jsonify(id=cursor.lastrowid, question=question, result=result, created_at=created), 201


@bp.get("/api/analyses/<analysis_id>/export")
def export_analysis(analysis_id):
    result = storage.serialize(get_analysis(analysis_id))
    result["detector"] = "TorchVision SSDLite320 MobileNetV3 / COCO_V1"
    result["minimum_detection_score"] = 0.25
    result["coordinate_system"] = "xyxy pixel coordinates on the saved, EXIF-oriented image"
    response = jsonify(result)
    response.headers["Content-Disposition"] = f'attachment; filename="nexa-{analysis_id}.json"'
    return response


@bp.delete("/api/analyses/<analysis_id>")
def delete_analysis(analysis_id):
    path = image_path(analysis_id)
    # Remove the image before committing deletion so filesystem errors are visible.
    path.unlink(missing_ok=True)
    with storage.db():
        storage.db().execute("DELETE FROM analyses WHERE id=?", (analysis_id,))
    return "", 204


def expand_visual_answer(result, analysis):
    """Explain the actual vision output; do not invent detail to pad its length."""
    result = dict(result)
    short = result["answer"]
    result["short_answer"] = short
    score = round(result["score"] * 100)
    labels = sorted({d["label"] for d in json.loads(analysis["detections"]) if d["score"] >= 0.5})
    result["answer"] = (
        f'The visual model’s best answer is “{short}”, with a model score of {score}%. '
        + (f'The object detector also identifies {", ".join(labels)} in this image. ' if labels else
           'The detector did not identify objects above the 50% confidence threshold. ')
        + "These are model predictions, so check the image before relying on this interpretation."
    )
    result["kind"] = "visual"
    result["sources"] = []
    return result


def get_conversation(conversation_id):
    row = storage.db().execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone()
    if row is None:
        abort(404, description="This conversation no longer exists.")
    return row


@bp.get("/api/conversations")
def list_conversations():
    rows = storage.db().execute("SELECT * FROM conversations ORDER BY updated_at DESC LIMIT 100").fetchall()
    return jsonify(conversations=[storage.conversation(row, False) for row in rows])


@bp.post("/api/conversations")
def create_conversation():
    conversation_id = uuid.uuid4().hex
    timestamp = storage.now()
    with storage.db():
        storage.db().execute("INSERT INTO conversations VALUES(?,?,?,?)", (conversation_id, "New conversation", timestamp, timestamp))
    return jsonify(storage.conversation(get_conversation(conversation_id))), 201


@bp.get("/api/conversations/<conversation_id>")
def retrieve_conversation(conversation_id):
    return jsonify(storage.conversation(get_conversation(conversation_id)))


@bp.delete("/api/conversations/<conversation_id>")
def delete_conversation(conversation_id):
    get_conversation(conversation_id)
    with storage.db():
        storage.db().execute("DELETE FROM conversations WHERE id=?", (conversation_id,))
    return "", 204


@bp.post("/api/conversations/<conversation_id>/messages")
def create_message(conversation_id):
    conversation = storage.conversation(get_conversation(conversation_id))
    payload = request.get_json(silent=True)
    question = payload.get("question") if isinstance(payload, dict) else None
    if not isinstance(question, str) or not question.strip() or len(question.strip()) > 1000:
        return jsonify(error="Enter a message between 1 and 1,000 characters."), 400
    question = question.strip()
    analysis_id = payload.get("analysis_id")
    if analysis_id is not None and not isinstance(analysis_id, str):
        return jsonify(error="Choose a valid saved image."), 400
    if payload.get("find_image", False) not in (True, False):
        return jsonify(error="find_image must be true or false."), 400
    history = conversation["messages"]
    previous_sources = next((m["result"].get("sources", []) for m in reversed(history) if m["result"].get("sources")), [])
    topic = learning_topic(question, previous_sources[0]["title"] if previous_sources else "")
    if analysis_id and re.match(r"^what\s+(is|are)\b", question, re.I) and not payload.get("find_image"):
        topic = ""
    if payload.get("find_image") and not topic:
        topic = previous_sources[0]["title"] if question.lower() in {"show me", "show me it", "show me an image"} and previous_sources else question[:160]
    result = None
    if analysis_id and not topic:
        path = image_path(analysis_id)
        try:
            with Image.open(path) as source:
                result = expand_visual_answer(vision().answer(source.convert("RGB"), question), get_analysis(analysis_id))
        except FileNotFoundError:
            abort(404, description="The saved image is missing.")
        except ValueError as error:
            return jsonify(error=str(error)), 400
    else:
        references = [current_app.extensions["knowledge"].search(topic)] if topic else previous_sources
        evidence = "\n\n".join(f"Topic: {s['title']}\nSource: {s['url']}\n{s['extract']}\nThe accompanying image is a topic illustration; do not invent its visual details."
                               for s in references[:1])
        prompt = (f"Explain {references[0]['title']} to a beginner in 3 to 5 sentences, using the supplied article. "
                  "The app displays the real illustration next to your answer. Do not describe a picture; explain the topic."
                  if topic and references else question)
        result = current_app.extensions["conversation"].reply(prompt, history, evidence)
        result["sources"] = references
        if references:
            result["kind"] = "learning"
            result["image_status"] = "found" if references[0].get("image_url") else "No illustration is available for this article."
    if len(result.get("answer", "").strip()) < 100:
        raise ModelUnavailable("The model returned an incomplete answer. Please retry or rephrase your message.")
    created = storage.now()
    if result.get("kind") == "visual":
        result["analysis_id"] = analysis_id
    try:
        with storage.db():
            cursor = storage.db().execute("INSERT INTO messages(conversation_id,question,result,created_at) VALUES(?,?,?,?)",
                                          (conversation_id, question, json.dumps(result), created))
            if result.get("kind") == "visual":
                storage.db().execute("INSERT INTO questions(analysis_id,question,result,created_at) VALUES(?,?,?,?)",
                                     (analysis_id, question, json.dumps(result), created))
            title = question[:70] if not history else conversation["title"]
            storage.db().execute("UPDATE conversations SET title=?,updated_at=? WHERE id=?", (title, created, conversation_id))
    except sqlite3.IntegrityError:
        abort(404, description="The conversation was deleted while processing this message.")
    return jsonify(id=cursor.lastrowid, question=question, result=result, created_at=created), 201


@bp.post("/api/voice/transcribe")
def transcribe_voice():
    upload = request.files.get("audio")
    if upload is None:
        return jsonify(error="Record a voice message first."), 400
    data = upload.stream.read(5 * 1024 * 1024 + 1)
    if not data or len(data) > 5 * 1024 * 1024:
        return jsonify(error="Record a non-empty voice message under 5 MB and 45 seconds."), 400
    try:
        transcript = current_app.extensions["conversation"].transcribe(data)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    return jsonify(text=transcript)
