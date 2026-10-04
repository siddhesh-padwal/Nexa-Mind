# Nexa Mind

A working, local Python + Flask visual intelligence app. Start a conversation without an image, speak a question, discover a topic through a real online illustration, or upload your own image for object detection. There is no API-key requirement or seeded conversation.

## Conversation and voice update

- **Text-only conversations:** a local Qwen2.5 0.5B instruction model generates replies and uses the last three conversation turns for follow-up context. Saved conversations reopen from the sidebar.
- **Learn with online images:** requests such as `Show me a volcano and explain it`, `Teach me about the solar system`, and `I want to learn about elephants` search Wikipedia. The app displays an actual associated image, article link, and image-credit link. A checkbox explicitly requests an image lookup when automatic topic detection does not recognize a phrase.
- **Voice input:** click **Speak**, allow microphone access, speak in English, and click **Finish recording**. Whisper transcribes locally. Review the editable transcript, then send it. Recording stops automatically after 40 seconds; the server rejects recordings longer than 45 seconds or larger than 5 MB. Audio is processed in memory and is not saved.
- **Spoken replies:** use **Read aloud** on an answer or enable **Read replies aloud**. **Stop reading** cancels playback. This uses your browser/system speech engine; available voices and offline behavior vary by browser. Edge or Chrome on localhost is recommended if the in-app browser does not provide microphone or speech support.
- **At least 100 characters:** every newly saved assistant answer contains at least 100 characters including spaces. The chat model is prompted for useful complete sentences and retried if too short; a still-incomplete answer returns a visible error. Image answers explain the actual predicted label, score, and detected objects. Historical answers saved before this update are preserved unchanged.
- **Conversation management:** reopen or delete chats separately from uploaded images. Removing an image from a chat does not delete the saved file. Visual messages also appear in the image's existing Q&A history.

Learning mode explains the linked article and displays its associated illustration. The text model does **not** directly inspect that internet image and cannot verify its visual details. It is a small CPU model and may make factual or conversational errors. General chat and uploaded-image inference work locally after setup. **Wikipedia searches and remote illustrations require internet access**; search topics are sent to Wikipedia and image requests go to Wikimedia. Uploaded images and microphone audio are not sent to an inference API. Lookup failures are shown as errors rather than substituted with unrelated pictures.

## Features

- JPEG, PNG, and WebP upload, drag-and-drop, and browser webcam snapshots.
- Real SSDLite object detection with bounding boxes, scores, confidence filtering, and per-label counts.
- Real ViLT visual question answering with expanded explanations, answer scores, alternative candidates, and a low-confidence indicator.
- SQLite-backed image and question history, reopening, permanent deletion, JSON export, and annotated PNG download.
- EXIF orientation correction, metadata removal, transparent-image normalization, and a maximum saved edge of 1600 pixels.
- Image validation: 8 MB upload limit, 20 megapixels, supported still-image formats only.
- Responsive interface, keyboard controls, visible progress/errors, retryable model loading, and a camera-permission failure state.
- Local inference and storage. A network connection is needed initially to download models and whenever Wikipedia images or articles are requested.

## Start after setup

After first-time setup, double-click `start.bat`, or run in PowerShell from this folder. The virtual environment and downloaded model cache are local files and are not included in the Git repository.

```powershell
.\start.ps1
```

Open **http://127.0.0.1:5000**. Wait for the relevant model notice to finish, then type a message, use Speak, or upload a photo. Stop the server with Ctrl+C. After an update, restart the server and refresh the page. If it is already running the current version, use the existing browser tab instead of launching a second copy.

## Fresh installation (Windows x64)

Clone the project and enter its directory:

```powershell
git clone https://github.com/siddhesh-padwal/Nexa-Mind.git
cd Nexa-Mind
```

Use Python **3.10–3.12**. Python 3.12 was used for validation. A CPU is sufficient; a GPU and paid API key are not required. Allow approximately 6 GB free disk space and at least 4 GB free RAM. Installation downloads CPU PyTorch and approximately 1.6 GB of pretrained vision, chat, and speech weights. The conversation model uses its native bfloat16 precision to reduce RAM use; speech recognition uses int8. Startup loads the vision and conversation models sequentially to avoid concurrent import failures. Replies can take tens of seconds depending on CPU speed and context length.

```powershell
.\setup.ps1 -Python "C:\Path\To\Python312\python.exe"
.\start.ps1
```

If PowerShell blocks local scripts, run the equivalent commands directly without changing the machine-wide execution policy:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe prepare_models.py
.\.venv\Scripts\python.exe run.py
```

The dependency file targets CPU Windows/Linux installations. macOS needs platform-appropriate Torch/TorchVision versions instead of the `+cpu` pins. Do not copy a virtual environment between computers; recreate it.

## Layout

```text
nexa-mind/
  nexa_mind/
    __init__.py          Flask factory, configuration, request safeguards
    routes.py            Image, question, history, export and health APIs
    storage.py           SQLite persistence and serialization
    services/
      images.py          Safe image decoding and normalization
      vision.py          Real TorchVision and ViLT inference
      conversation.py    Local Qwen conversation and Whisper speech recognition
      knowledge.py       Live Wikipedia article and illustration retrieval
    templates/index.html
    static/              CSS, vanilla JavaScript and favicon
  tests/                 API, validation and persistence tests
  run.py                 Waitress server bound to loopback
  prepare_models.py      Model download/load verification
  setup.ps1              Dependency and model setup
  start.ps1 / start.bat  Launchers
  requirements.txt
  requirements-lock.txt Exact validated environment (after installation)
  instance/              Generated local data; excluded from source control
    models/              Downloaded pretrained model cache
    uploads/             Normalized images
    nexa.sqlite3         Analyses and Q&A
    .secret              Persistent local session signing key
```

## How inference works

1. Flask validates the upload, corrects its orientation, removes metadata, flattens transparency onto white, and limits its size.
2. [TorchVision SSDLite320 MobileNetV3](https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.detection.ssdlite320_mobilenet_v3_large.html), trained on COCO, detects supported object classes. Predictions at scores of 0.25 or higher are stored. The interface initially displays scores of 0.50 or higher.
3. [ViLT fine-tuned on VQAv2](https://huggingface.co/dandelin/vilt-b32-finetuned-vqa) processes the saved image and the question together. It returns short answers from a fixed answer vocabulary, rather than generating unrestricted prose. The model revision is pinned.
4. Every successful question and its result are stored in SQLite. AI requests are serialized to bound CPU and RAM usage. Concurrent inference requests receive a retryable 503 response.
5. Text-only messages use Qwen2.5-0.5B-Instruct (pinned revision), with the last three exchanges as context. Learning requests retrieve the Wikipedia article and illustration before generation. Follow-ups reuse the previous article until a new topic is requested.
6. English voice recordings are decoded with PyAV, duration-checked, and transcribed with `Systran/faster-whisper-tiny.en` (pinned revision) using int8 CPU inference.

Model scores are **not calibrated probabilities**. A score below 0.5 triggers the low-confidence label, but a higher score does not ensure correctness. Object counts are detector counts, not guaranteed scene totals. ViLT cannot reliably refuse every unanswerable question. Uploaded-image questions still use its short-answer vocabulary, with a factual explanation of model output added around it; this is not free-form image reasoning. Visual follow-up questions must explicitly name their subject. General text conversations use the separate language model and do have recent conversational context. The detector recognizes COCO categories; it cannot detect every possible object. Camera support captures a single still image, not continuous video detection.

Examples of suitable questions: `What animal is shown?`, `What color is the car?`, `What is the person holding?`, `Is the person sitting?` Results depend on the image and may be incorrect.

## Configuration and offline use

- `NEXA_PORT`: listening port, defaults to `5000`.
- `NEXA_DATA_DIR`: absolute location for images, database, secrets, and model cache; defaults to `instance/` inside the project.
- After successful model preparation, set `HF_HUB_OFFLINE=1` for strict offline operation. Otherwise Hugging Face may check model metadata when loading, without sending images.
- Offline model loading does not make internet image search available offline. Those requests still need Wikipedia/Wikimedia access. Browser speech voices may require an internet connection depending on the installed voice.

```powershell
$env:HF_HUB_OFFLINE = "1"
$env:NEXA_PORT = "5000"
.\.venv\Scripts\python.exe run.py
```

The app is a **single-user local application**. All browser sessions on this computer share the same history (the latest 100 images appear in the sidebar). It deliberately listens on `127.0.0.1` and has no account system. Do not expose it publicly without adding authentication, per-user data isolation, TLS, rate limiting, and deployment-specific storage controls. Local requests use CSRF tokens and trusted-host checks.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pip check
```

API tests use explicitly labeled test doubles to exercise validation, persistence, failure cases, and request protection without downloading models. These doubles exist only in `tests/`. Real inference and browser checks are reported separately in `VALIDATION.md`; unit-test success alone does not prove model inference works.

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/status` | Model readiness |
| POST | `/api/models/load` | Start or retry model loading |
| GET / POST | `/api/analyses` | Recent history / multipart image upload |
| GET / DELETE | `/api/analyses/<id>` | Reopen / remove an analysis and its questions |
| GET | `/api/analyses/<id>/image` | Normalized JPEG |
| POST | `/api/analyses/<id>/questions` | JSON body with `question` |
| GET | `/api/analyses/<id>/export` | Download JSON results |
| GET / POST | `/api/conversations` | List / create a text or mixed conversation |
| GET / DELETE | `/api/conversations/<id>` | Reopen / delete conversation |
| POST | `/api/conversations/<id>/messages` | JSON `question`, optional `analysis_id` and `find_image` |
| POST | `/api/voice/transcribe` | Multipart `audio`; returns an editable transcript |

Mutation requests require the session cookie and `X-CSRF-Token` from the page's `csrf-token` meta tag. Exports include all stored detections at or above 0.25, independent of the current UI threshold. PNG downloads use the currently displayed threshold and box-visibility setting.

## Troubleshooting

- **Models unavailable:** check the terminal traceback, internet connection, disk space, and memory, then click Retry loading or rerun `prepare_models.py`. The app never supplies placeholder results.
- **Port in use:** use the existing server or choose another `NEXA_PORT`.
- **Camera denied/unavailable:** allow camera access on localhost, close another app using the camera, or upload a photo. Physical camera access depends on browser and hardware.
- **Long first start:** downloading weights is a one-time operation. Later starts load the local cache into RAM.
- **No detections:** lower the confidence threshold or use a clearer image of supported objects. VQA remains available when the detector finds nothing.
- **Question too long:** keep it below 300 characters and 40 model tokens (roughly 25–30 words).
- **Text message too long:** general chat permits 1,000 characters. ViLT image questions remain subject to its 40-token limit.
- **Microphone denied:** allow microphone access for `http://127.0.0.1:5000` in the browser, then click Speak again. Voice recording does not start automatically.
- **No spoken playback:** use Read aloud again, check the system volume and installed voices, or open the app in Edge/Chrome.
- **Wikipedia unavailable/no image:** retry with an internet connection and a specific topic. Not every article has an illustration.

The Flask, TorchVision, Transformers, Qwen, and Whisper libraries/models retain their upstream licenses. Retrieved Wikipedia text and Wikimedia illustrations retain their original attribution and licensing requirements; source and image-credit links are shown in the app. Review upstream licenses before redistribution.
