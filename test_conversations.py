import io
import pytest
from nexa_mind.services.knowledge import learning_topic, KnowledgeUnavailable
from nexa_mind.storage import db


def new(client, csrf):
    response = client.post('/api/conversations', headers=csrf)
    assert response.status_code == 201
    return response.json['id']


def send(client, csrf, conversation_id, question, **extra):
    return client.post(f'/api/conversations/{conversation_id}/messages', headers=csrf, json={'question': question, **extra})


def test_text_only_chat_and_persistence(app, client, csrf):
    cid = new(client, csrf)
    first = send(client, csrf, cid, 'Hi there')
    assert first.status_code == 201
    assert len(first.json['result']['answer']) >= 100
    assert send(client, csrf, cid, 'Can you explain more?').status_code == 201
    assert len(app.extensions['conversation'].last_history) == 1
    saved = client.get(f'/api/conversations/{cid}').json
    assert len(saved['messages']) == 2
    assert saved['title'] == 'Hi there'
    assert client.get('/api/conversations').json['conversations'][0]['id'] == cid
    assert client.delete(f'/api/conversations/{cid}', headers=csrf).status_code == 204
    assert client.get(f'/api/conversations/{cid}').status_code == 404
    with app.app_context():
        assert db().execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 0


def test_learning_source_and_followup_context(app, client, csrf):
    cid = new(client, csrf)
    first = send(client, csrf, cid, 'Show me a volcano and explain it')
    assert first.status_code == 201
    assert first.json['result']['sources'][0]['image_url']
    assert 'planetary crust' in app.extensions['conversation'].last_evidence
    second = send(client, csrf, cid, 'Why does it erupt?')
    assert second.status_code == 201
    assert second.json['result']['sources'][0]['title'] == 'Volcano'
    assert len(app.extensions['conversation'].last_history) == 1


def test_short_answer_rejected_instead_of_padded(app, client, csrf):
    cid = new(client, csrf)
    app.extensions['conversation'].reply = lambda *args: {'answer': 'Too short'}
    response = send(client, csrf, cid, 'Hello')
    assert response.status_code == 503
    assert client.get(f'/api/conversations/{cid}').json['messages'] == []


def test_lookup_failure_does_not_create_fake_image(app, client, csrf):
    cid = new(client, csrf)
    def fail(topic):
        raise KnowledgeUnavailable('Service unavailable')
    app.extensions['knowledge'].search = fail
    assert send(client, csrf, cid, 'Teach me about volcanoes').status_code == 503
    assert client.get(f'/api/conversations/{cid}').json['messages'] == []


@pytest.mark.parametrize('question', ['', '   ', None, 5, 'x' * 1001])
def test_invalid_message(client, csrf, question):
    assert send(client, csrf, new(client, csrf), question).status_code == 400


@pytest.mark.parametrize('question,expected', [
    ('Show me a volcano and explain it', 'volcano'), ('I want to learn about elephants', 'elephants'),
    ('Teach me about the solar system', 'solar system'), ('What is photosynthesis?', 'photosynthesis'),
    ('Hi there', ''), ('Explain more', ''), ('What is in the picture?', ''), ('Show me it', 'Volcano'),
])
def test_topic_routing(question, expected):
    assert learning_topic(question, 'Volcano') == expected


def test_voice_upload_and_errors(client, csrf):
    assert client.post('/api/voice/transcribe', headers=csrf).status_code == 400
    assert client.post('/api/voice/transcribe', data={'audio': (io.BytesIO(b'voice-fixture'), 'test.webm')}).status_code == 403
    response = client.post('/api/voice/transcribe', headers=csrf, data={'audio': (io.BytesIO(b'voice-fixture'), 'test.webm')})
    assert response.json['text'] == 'Teach me about volcanoes'
    assert client.post('/api/voice/transcribe', headers=csrf, data={'audio': (io.BytesIO(b'invalid'), 'test.webm')}).status_code == 400
    assert client.post('/api/voice/transcribe', headers=csrf, data={'audio': (io.BytesIO(b'x' * (5 * 1024 * 1024 + 1)), 'large.webm')}).status_code == 400
    assert 'microphone=(self)' in client.get('/').headers['Permissions-Policy']


def test_visual_message_preserves_image_history(client, csrf):
    from test_api import upload
    analysis_id = upload(client, csrf).json['id']
    cid = new(client, csrf)
    response = send(client, csrf, cid, 'What is the person holding?', analysis_id=analysis_id)
    assert response.status_code == 201
    assert response.json['result']['kind'] == 'visual'
    assert len(response.json['result']['answer']) >= 100
    assert client.get(f'/api/analyses/{analysis_id}').json['questions'][0]['result']['short_answer'] == 'fixture-answer'
