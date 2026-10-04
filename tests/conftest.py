"""Deterministic doubles ONLY for API tests; never used by the running app."""
import pytest
from nexa_mind import create_app


class TestVision:
    def status(self):
        return {"state": "ready", "detail": "Test fixture", "detector": True, "vqa": True}

    def start(self):
        pass

    def detect(self, image):
        return [{"label": "fixture-object", "score": 0.9, "box": [0, 0, image.width, image.height]}]

    def answer(self, image, question):
        return {"answer": "fixture-answer", "score": 0.9, "uncertain": False, "alternatives": [], "model": "test-only"}


class TestConversation:
    def status(self):
        return {"state": "ready", "detail": "Test fixture", "chat": True, "speech": True}

    def start(self):
        pass

    def reply(self, question, history, evidence=""):
        self.last_history = history
        self.last_evidence = evidence
        return {"answer": "This is a deterministic response used only in automated tests. It is long enough to verify the requested minimum response length.",
                "kind": "conversation", "sources": [], "model": "test-only"}

    def transcribe(self, data):
        if data == b"invalid":
            raise ValueError("Invalid recording")
        return "Teach me about volcanoes"


class TestKnowledge:
    def search(self, topic):
        return {"title": "Volcano", "url": "https://en.wikipedia.org/wiki/Volcano", "provider": "Wikipedia",
                "extract": "A volcano is an opening in a planetary crust through which hot lava, ash, and gases escape. This text is an explicit test fixture.",
                "image_url": "https://upload.wikimedia.org/test.jpg", "image_page": "https://en.wikipedia.org/wiki/File:test.jpg"}


@pytest.fixture
def app(tmp_path):
    return create_app({"TESTING": True, "DATA_DIR": tmp_path, "SECRET_KEY": "test-secret", "VISION_SERVICE": TestVision(),
                       "CONVERSATION_SERVICE": TestConversation(), "KNOWLEDGE_SERVICE": TestKnowledge()})


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def csrf(client):
    client.get("/")
    with client.session_transaction() as session:
        return {"X-CSRF-Token": session["csrf"]}
