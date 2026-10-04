'use strict';
const $ = (id) => document.getElementById(id);
const token = document.querySelector('meta[name="csrf-token"]').content;
const state = { current: null, conversation: null, image: null, ready: false, chatReady: false, speechReady: false, busy: false, stream: null, selection: 0, recording: false };
const colors = ['#2d9d77', '#5486c4', '#c57b36', '#a368ac', '#bc5965'];

async function api(url, options = {}) {
  const response = await fetch(url, { ...options, headers: { 'X-CSRF-Token': token, ...options.headers } });
  if (response.status === 204) return null;
  const payload = await response.json().catch(() => ({ error: `Server returned ${response.status}.` }));
  if (!response.ok) throw new Error(payload.error || 'The request failed. Please try again.');
  return payload;
}
function showError(error) { $('error-text').textContent = error.message || String(error); $('error-banner').hidden = false; }
function clearError() { $('error-banner').hidden = true; }
function updateControls() {
  const unavailable = !state.ready || state.busy || state.recording;
  $('choose-image').disabled = unavailable; $('open-camera').disabled = unavailable;
  $('new-analysis').disabled = state.busy; $('delete-analysis').disabled = state.busy;
  const canChat = state.current ? state.ready : state.chatReady;
  $('question').disabled = !canChat || state.busy || state.recording;
  $('ask-button').disabled = !canChat || state.busy || state.recording || !$('question').value.trim();
  $('question').placeholder = state.current ? 'Ask about this image, or request a new topic…' : 'Ask anything, or say what you want to learn…';
  $('record-voice').disabled = state.busy || (!state.speechReady && !state.recording);
  $('record-voice').textContent = state.recording ? '■ Finish recording' : '● Speak';
  $('new-analysis').disabled = state.busy || state.recording;
  $('delete-conversation').hidden = !state.conversation;
  $('delete-conversation').disabled = state.busy || state.recording;
  $('detach-image').disabled = state.busy || state.recording;
  document.querySelectorAll('.suggestion').forEach(button => { button.disabled = !state.chatReady || state.busy || state.recording; });
  document.querySelectorAll('.history-item').forEach(button => { button.disabled = state.busy || state.recording; });
}
async function checkStatus() {
  try {
    const status = await api('/api/status');
    state.ready = status.state === 'ready';
    state.chatReady = Boolean(status.conversation?.chat);
    state.speechReady = Boolean(status.conversation?.speech);
    $('conversation-detail').textContent = status.conversation?.detail || 'Restart the server to load the conversation update.';
    $('conversation-notice').hidden = status.conversation?.state === 'ready';
    $('retry-conversation').hidden = !['error', 'not_loaded'].includes(status.conversation?.state);
    $('status-pill').dataset.state = status.state;
    $('status-pill').lastElementChild.textContent = { ready: 'Local models ready', loading: 'Loading AI models', error: 'Models unavailable', not_loaded: 'Models not loaded' }[status.state];
    $('model-detail').textContent = status.detail;
    $('model-notice').hidden = state.ready;
    $('retry-models').hidden = !['error', 'not_loaded'].includes(status.state);
    updateControls();
  } catch (error) {
    state.ready = false; state.chatReady = false; state.speechReady = false; updateControls();
    $('status-pill').dataset.state = 'error'; $('status-pill').lastElementChild.textContent = 'Server disconnected';
    $('model-notice').hidden = false; $('model-detail').textContent = 'Cannot reach the local server. Check that Nexa Mind is running.';
  }
}
function element(tag, className, text) {
  const el = document.createElement(tag); if (className) el.className = className;
  if (text !== undefined) el.textContent = text; return el;
}
async function refreshHistory() {
  const { analyses } = await api('/api/analyses');
  $('history').replaceChildren(); $('history-count').textContent = analyses.length;
  if (!analyses.length) $('history').append(element('p', 'history-empty', 'Your images will appear here.'));
  for (const analysis of analyses) {
    const button = element('button', `history-item${state.current?.id === analysis.id ? ' active' : ''}`);
    const thumb = element('img'); thumb.src = analysis.image_url; thumb.alt = ''; thumb.loading = 'lazy';
    const text = element('div'); text.append(element('strong', '', analysis.name), element('small', '', new Date(analysis.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })));
    button.append(thumb, text); button.title = analysis.name;
    button.addEventListener('click', () => openAnalysis(analysis.id)); $('history').append(button);
  }
  updateControls();
}
async function refreshConversations() {
  const { conversations } = await api('/api/conversations');
  $('conversation-history').replaceChildren(); $('conversation-count').textContent = conversations.length;
  for (const conversation of conversations) {
    const button = element('button', `history-item conversation-item${state.conversation?.id === conversation.id ? ' active' : ''}`);
    button.append(element('span', 'conversation-glyph', '◌'), element('strong', '', conversation.title));
    button.title = conversation.title; button.addEventListener('click', () => openConversation(conversation.id));
    $('conversation-history').append(button);
  }
  updateControls();
}
async function openConversation(id) {
  if (state.busy || state.recording) return;
  const selection = ++state.selection;
  try {
    const conversation = await api(`/api/conversations/${id}`);
    if (selection !== state.selection) return;
    state.conversation = conversation; detachImage();
    $('chat-messages').replaceChildren(); $('chat-empty').hidden = conversation.messages.length > 0;
    for (const item of conversation.messages) appendAnswer(item);
    const last = conversation.messages.at(-1);
    if (last?.result.analysis_id) {
      try { const analysis = await api(`/api/analyses/${last.result.analysis_id}`); await displayAnalysis(analysis, selection, true); }
      catch { $('voice-status').textContent = 'The earlier image is no longer available. This conversation is still saved.'; }
    }
    clearError(); await refreshConversations();
  } catch (error) { showError(error); }
}
async function openAnalysis(id) {
  if (state.busy || state.recording) return;
  const selection = ++state.selection;
  try {
    clearError();
    const analysis = await api(`/api/analyses/${id}`);
    if (selection !== state.selection) return;
    await displayAnalysis(analysis, selection);
    await refreshHistory();
  } catch (error) { if (selection === state.selection) showError(error); }
}
async function displayAnalysis(analysis, selection = ++state.selection, preserveChat = false) {
  const image = new Image(); image.src = analysis.image_url;
  await image.decode();
  if (selection !== state.selection) return;
  state.current = analysis; state.image = image;
  $('drop-zone').hidden = true; $('image-workspace').hidden = false;
  $('discovered-image').hidden = true;
  $('image-size').textContent = `${analysis.width} × ${analysis.height} px`;
  $('export-json').href = `/api/analyses/${analysis.id}/export`;
  if (!preserveChat) {
    state.conversation = null;
    $('chat-messages').replaceChildren();
    for (const question of analysis.questions) appendAnswer(question);
    $('chat-empty').hidden = analysis.questions.length > 0;
  }
  $('question').value = ''; $('char-count').textContent = '0 / 1000';
  drawDetections(); updateControls();
}
function filteredDetections() { return (state.current?.detections || []).filter(d => d.score >= Number($('confidence').value) / 100); }
function drawDetections() {
  if (!state.image || !state.current) return;
  const canvas = $('image-canvas'); const ctx = canvas.getContext('2d');
  canvas.width = state.current.width; canvas.height = state.current.height;
  ctx.drawImage(state.image, 0, 0, canvas.width, canvas.height);
  const detections = filteredDetections(); const groups = new Map();
  for (const item of detections) groups.set(item.label, (groups.get(item.label) || 0) + 1);
  const labels = [...groups.keys()];
  if ($('show-boxes').checked) for (const detection of detections) {
    const [x1, y1, x2, y2] = detection.box; const color = colors[labels.indexOf(detection.label) % colors.length];
    const fontSize = Math.max(13, Math.round(canvas.width / 45)); const pad = fontSize * 0.4;
    ctx.lineWidth = Math.max(2, canvas.width / 350); ctx.strokeStyle = color; ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
    const text = `${detection.label} ${Math.round(detection.score * 100)}%`;
    ctx.font = `600 ${fontSize}px Segoe UI, sans-serif`;
    const width = Math.min(canvas.width, ctx.measureText(text).width + pad * 2); const height = fontSize + pad * 2;
    const left = Math.max(0, Math.min(x1, canvas.width - width)); const top = Math.max(0, y1 - height);
    ctx.fillStyle = color; ctx.fillRect(left, top, width, height); ctx.fillStyle = '#fff'; ctx.fillText(text, left + pad, top + pad + fontSize * 0.8);
  }
  $('object-count').textContent = detections.length; $('confidence-value').textContent = `${$('confidence').value}%`;
  $('detection-list').replaceChildren();
  for (const [label, count] of groups) { const chip = element('span', 'object-chip', label); chip.append(element('strong', '', `× ${count}`)); $('detection-list').append(chip); }
  if (!detections.length) $('detection-list').append(element('p', 'no-detections', 'No objects detected at this confidence. Try a lower threshold or a clearer image. You can still ask a visual question.'));
}
function appendAnswer(item) {
  $('chat-empty').hidden = true;
  const entry = element('article', 'chat-entry');
  const result = item.result;
  entry.append(element('div', 'message-label', 'YOU'), element('div', 'user-message', item.question), element('div', 'message-label', 'NEXA MIND'));
  const answer = element('div', 'answer-message', result.answer);
  if (typeof result.score === 'number') answer.append(element('div', `answer-score${result.uncertain ? ' uncertain' : ''}`, `${result.uncertain ? 'Low confidence · ' : ''}Model score ${Math.round(result.score * 100)}%`));
  if (result.uncertain) answer.append(element('div', 'alternatives', 'Please verify this answer against the image.'));
  const details = element('details', 'alternatives'); details.append(element('summary', '', 'Other model candidates'));
  for (const candidate of result.alternatives || []) details.append(element('div', '', `${candidate.answer} · ${Math.round(candidate.score * 100)}%`));
  if (result.alternatives?.length) answer.append(details);
  for (const source of result.sources || []) {
    const link = element('a', 'source-link', `Source: ${source.title} · ${source.provider}`);
    link.href = safeLink(source.url); link.target = '_blank'; link.rel = 'noopener noreferrer'; answer.append(link);
  }
  if (result.sources?.length) showDiscoveredImage(result.sources[0]);
  const speak = element('button', 'text-button read-answer', '▷ Read aloud'); speak.type = 'button';
  speak.addEventListener('click', () => speakAnswer(result.answer)); answer.append(speak);
  entry.append(answer); $('chat-messages').append(entry);
  $('chat-messages').scrollTop = $('chat-messages').scrollHeight;
}
async function uploadImage(file) {
  if (!file || state.busy) return;
  if (!state.ready) { showError(new Error('Please wait until the local AI models are ready.')); return; }
  if (file.size > 8 * 1024 * 1024) { showError(new Error('Choose an image under 8 MB.')); return; }
  clearError(); state.busy = true; ++state.selection; updateControls(); $('upload-progress').hidden = false;
  try {
    const body = new FormData(); body.append('image', file);
    const analysis = await api('/api/analyses', { method: 'POST', body });
    await displayAnalysis(analysis, ++state.selection, Boolean(state.conversation)); await refreshHistory();
  } catch (error) { showError(error); }
  finally { state.busy = false; $('upload-progress').hidden = true; $('file-input').value = ''; updateControls(); }
}
function resetWorkspace() {
  ++state.selection; state.current = null; state.conversation = null; state.image = null;
  $('drop-zone').hidden = false; $('image-workspace').hidden = true; $('chat-empty').hidden = false;
  $('chat-messages').replaceChildren(); $('question').value = ''; $('char-count').textContent = '0 / 1000';
  $('discovered-image').hidden = true; $('find-image').checked = false; stopSpeaking();
  $('image-size').textContent = 'Your starting point'; clearError(); updateControls();
  refreshHistory().catch(showError);
  refreshConversations().catch(showError);
}
$('choose-image').addEventListener('click', () => $('file-input').click());
$('file-input').addEventListener('change', e => uploadImage(e.target.files[0]));
$('new-analysis').addEventListener('click', resetWorkspace);
$('dismiss-error').addEventListener('click', clearError);
$('retry-models').addEventListener('click', async () => { try { await api('/api/models/load', { method: 'POST' }); await checkStatus(); } catch (error) { showError(error); } });
$('retry-conversation').addEventListener('click', () => $('retry-models').click());
for (const name of ['dragenter', 'dragover']) $('drop-zone').addEventListener(name, e => { e.preventDefault(); $('drop-zone').classList.add('drag-over'); });
for (const name of ['dragleave', 'drop']) $('drop-zone').addEventListener(name, e => { e.preventDefault(); $('drop-zone').classList.remove('drag-over'); });
$('drop-zone').addEventListener('drop', e => uploadImage(e.dataTransfer.files[0]));
window.addEventListener('dragover', e => e.preventDefault()); window.addEventListener('drop', e => e.preventDefault());
$('confidence').addEventListener('input', drawDetections); $('show-boxes').addEventListener('change', drawDetections);
$('question').addEventListener('input', () => { $('char-count').textContent = `${$('question').value.length} / 1000`; updateControls(); });
$('question').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); if (!$('ask-button').disabled) $('question-form').requestSubmit(); } });
document.querySelectorAll('.suggestion').forEach(button => button.addEventListener('click', () => { $('question').value = button.dataset.question; $('question').dispatchEvent(new Event('input')); $('question').focus(); }));
$('question-form').addEventListener('submit', async e => {
  e.preventDefault(); const question = $('question').value.trim();
  if (!question || state.busy || state.recording || !(state.current ? state.ready : state.chatReady)) return;
  state.busy = true; stopSpeaking(); clearError(); updateControls(); $('thinking').hidden = false;
  try {
    if (!state.conversation) state.conversation = await api('/api/conversations', { method: 'POST' });
    const item = await api(`/api/conversations/${state.conversation.id}/messages`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, analysis_id: state.current?.id || null, find_image: $('find-image').checked }) });
    state.conversation.messages.push(item); appendAnswer(item); $('question').value = ''; $('char-count').textContent = '0 / 1000';
    $('find-image').checked = false; await refreshConversations();
    if ($('auto-speak').checked) speakAnswer(item.result.answer);
  } catch (error) { showError(error); }
  finally { state.busy = false; $('thinking').hidden = true; updateControls(); $('question').focus(); }
});
$('download-image').addEventListener('click', () => {
  const analysisId = state.current?.id; if (!analysisId) return;
  $('image-canvas').toBlob(blob => { if (!blob) return; const url = URL.createObjectURL(blob); const link = element('a'); link.href = url; link.download = `nexa-${analysisId}.png`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }, 'image/png');
});
$('delete-analysis').addEventListener('click', () => $('delete-dialog').showModal());
$('cancel-delete').addEventListener('click', () => $('delete-dialog').close());
$('confirm-delete').addEventListener('click', async () => {
  if (!state.current || state.busy) return;
  state.busy = true; updateControls(); $('confirm-delete').disabled = true;
  try { await api(`/api/analyses/${state.current.id}`, { method: 'DELETE' }); $('delete-dialog').close(); resetWorkspace(); }
  catch (error) { $('delete-dialog').close(); showError(error); }
  finally { state.busy = false; $('confirm-delete').disabled = false; updateControls(); }
});
function stopCamera() { if (state.stream) state.stream.getTracks().forEach(track => track.stop()); state.stream = null; $('camera-video').srcObject = null; $('capture-photo').disabled = true; }
$('open-camera').addEventListener('click', async () => {
  $('camera-error').textContent = ''; $('camera-dialog').showModal();
  try {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('Camera access requires localhost or HTTPS and a supported browser.');
    const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment', width: { ideal: 1280 } }, audio: false });
    if (!$('camera-dialog').open) { stream.getTracks().forEach(track => track.stop()); return; }
    state.stream = stream; $('camera-video').srcObject = stream; await $('camera-video').play();
    $('capture-photo').disabled = false;
  } catch (error) { stopCamera(); $('camera-error').textContent = error.name === 'NotAllowedError' ? 'Camera permission was denied. Allow camera access in your browser, or upload an image.' : `Camera unavailable: ${error.message}`; }
});
$('close-camera').addEventListener('click', () => $('camera-dialog').close());
$('camera-dialog').addEventListener('close', stopCamera);
$('camera-dialog').addEventListener('cancel', stopCamera);
window.addEventListener('pagehide', stopCamera);
$('capture-photo').addEventListener('click', () => {
  const video = $('camera-video'); if (!video.videoWidth) return;
  $('capture-photo').disabled = true;
  const canvas = document.createElement('canvas'); canvas.width = video.videoWidth; canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video, 0, 0);
  canvas.toBlob(blob => { $('camera-dialog').close(); stopCamera(); if (blob) uploadImage(new File([blob], `camera-${Date.now()}.jpg`, { type: 'image/jpeg' })); else showError(new Error('Could not capture a frame. Please try again.')); }, 'image/jpeg', 0.92);
});
function safeLink(value) {
  try { const url = new URL(value); return url.protocol === 'https:' ? url.href : '#'; } catch { return '#'; }
}
function detachImage() {
  state.current = null; state.image = null; $('image-workspace').hidden = true;
  $('discovered-image').hidden = true; $('drop-zone').hidden = false; $('image-size').textContent = 'Optional image'; updateControls();
}
$('detach-image').addEventListener('click', detachImage);
function showDiscoveredImage(source) {
  state.current = null; state.image = null; $('image-workspace').hidden = true; $('drop-zone').hidden = true;
  const panel = $('discovered-image'); panel.replaceChildren(); panel.hidden = false;
  panel.append(element('p', 'eyebrow', 'FOUND ON WIKIPEDIA'), element('h3', '', source.title));
  if (source.image_url) {
    const image = element('img', 'web-image'); image.src = safeLink(source.image_url); image.alt = `Wikipedia illustration: ${source.title}`;
    image.referrerPolicy = 'no-referrer';
    image.addEventListener('error', () => { image.hidden = true; panel.append(element('p', 'micro-note', 'The image could not load. Open the source page to view it.')); });
    panel.append(image, element('p', 'image-credit', source.image_title?.replaceAll('_', ' ') || source.title));
    const credits = element('a', 'source-link', 'Image credits & license ↗'); credits.href = safeLink(source.image_page); credits.target = '_blank'; credits.rel = 'noopener noreferrer'; panel.append(credits);
  } else panel.append(element('p', 'micro-note', 'This article does not provide an illustration. Try another topic to see an image.'));
  panel.append(element('p', 'micro-note', 'This is an illustration associated with the source article. The explanation draws on that article; it is not a verified visual description.'));
  const article = element('a', 'source-link', 'Read the source article ↗'); article.href = safeLink(source.url); article.target = '_blank'; article.rel = 'noopener noreferrer';
  const addImage = element('button', 'text-button', 'Use my own image instead'); addImage.type = 'button'; addImage.addEventListener('click', detachImage);
  panel.append(article, addImage); $('image-size').textContent = 'Online discovery'; updateControls();
}
let speechUtterance = null;
function stopSpeaking() { if ('speechSynthesis' in window) window.speechSynthesis.cancel(); speechUtterance = null; $('stop-speaking').hidden = true; }
function speakAnswer(text) {
  stopSpeaking();
  if (!('speechSynthesis' in window)) { showError(new Error('Spoken playback is unavailable in this browser. Open Nexa Mind in Edge or Chrome.')); return; }
  speechUtterance = new SpeechSynthesisUtterance(text); speechUtterance.lang = 'en-US'; speechUtterance.rate = 1;
  speechUtterance.onend = () => { $('stop-speaking').hidden = true; };
  speechUtterance.onerror = event => {
    $('stop-speaking').hidden = true;
    if (!['interrupted', 'canceled'].includes(event.error)) $('voice-status').textContent = 'Playback could not start. Try Read aloud again or use Edge/Chrome with a system voice installed.';
  };
  $('stop-speaking').hidden = false; window.speechSynthesis.speak(speechUtterance);
}
$('stop-speaking').addEventListener('click', stopSpeaking);
$('auto-speak').addEventListener('change', () => { if (!$('auto-speak').checked) stopSpeaking(); });
const voice = { recorder: null, stream: null, timer: null, canceled: false };
function releaseMicrophone() {
  clearTimeout(voice.timer); voice.timer = null;
  if (voice.stream) voice.stream.getTracks().forEach(track => track.stop()); voice.stream = null;
}
$('record-voice').addEventListener('click', async () => {
  if (state.recording) { if (voice.recorder?.state === 'recording') voice.recorder.stop(); return; }
  if (state.busy || !state.speechReady) return;
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) { showError(new Error('Microphone recording requires a supported browser on localhost or HTTPS. Try Edge or Chrome.')); return; }
  stopSpeaking(); clearError(); state.busy = true; updateControls(); $('voice-status').textContent = 'Waiting for microphone permission…';
  try {
    voice.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true }, video: false });
    const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find(type => MediaRecorder.isTypeSupported(type));
    voice.recorder = new MediaRecorder(voice.stream, mime ? { mimeType: mime } : {});
    voice.canceled = false; const chunks = [];
    voice.recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
    voice.recorder.onerror = () => { voice.canceled = true; releaseMicrophone(); state.recording = false; state.busy = false; updateControls(); showError(new Error('Recording failed. Try again or type your message.')); };
    voice.recorder.onstop = async () => {
      const type = voice.recorder.mimeType || 'audio/webm'; releaseMicrophone(); state.recording = false;
      if (voice.canceled) { state.busy = false; updateControls(); return; }
      state.busy = true; updateControls(); $('voice-status').textContent = 'Transcribing your voice locally…';
      try {
        const body = new FormData(); body.append('audio', new Blob(chunks, { type }), 'voice-message');
        const result = await api('/api/voice/transcribe', { method: 'POST', body });
        $('question').value = result.text; $('question').dispatchEvent(new Event('input'));
        $('voice-status').textContent = 'Transcribed. Review your message, then press Send.';
      } catch (error) { showError(error); $('voice-status').textContent = 'Transcription failed. You can try again or type your question.'; }
      finally { state.busy = false; updateControls(); $('question').focus(); }
    };
    voice.recorder.start(250); state.recording = true; state.busy = false; updateControls();
    $('voice-status').textContent = 'Listening… Click Finish recording when done (40 seconds maximum).';
    voice.timer = setTimeout(() => { if (voice.recorder?.state === 'recording') voice.recorder.stop(); }, 40000);
  } catch (error) {
    releaseMicrophone(); state.busy = false; state.recording = false; updateControls();
    $('voice-status').textContent = error.name === 'NotAllowedError' ? 'Microphone permission was denied. Allow access in your browser and try again.' : `Microphone unavailable: ${error.message}`;
  }
});
window.addEventListener('pagehide', () => { voice.canceled = true; if (voice.recorder?.state === 'recording') voice.recorder.stop(); releaseMicrophone(); stopSpeaking(); });
$('delete-conversation').addEventListener('click', async () => {
  if (!state.conversation || state.busy || !window.confirm('Delete this conversation and its messages? Uploaded images will remain in Recent images.')) return;
  state.busy = true; updateControls();
  try { await api(`/api/conversations/${state.conversation.id}`, { method: 'DELETE' }); resetWorkspace(); }
  catch (error) { showError(error); }
  finally { state.busy = false; updateControls(); }
});
updateControls();
checkStatus(); refreshHistory().catch(showError); refreshConversations().catch(showError);
setInterval(checkStatus, 5000);
