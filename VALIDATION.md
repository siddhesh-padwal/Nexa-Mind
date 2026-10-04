# Nexa Mind validation — 4 October 2026

## Automated backend checks

- **38 tests passed** using `python -m pytest`.
- `pip check` reported no broken requirements.
- JavaScript syntax validation passed with `node --check nexa_mind/static/app.js`.
- Tests cover image validation and persistence, request protection, conversation creation/reopening/deletion, recent conversation context, topic routing, source handling, short-answer rejection, microphone upload limits, and preserving uploaded-image Q&A history.
- Deterministic test doubles are confined to the unit tests. They are not used in the running application.

## Real-model and browser verification

The running Flask/Waitress server used the downloaded SSDLite, ViLT, Qwen2.5-0.5B-Instruct and Whisper tiny.en models. Qwen uses its native bfloat16 weights; the experimental dynamic-int8 conversation configuration was removed because it reduced answer quality.

Verified in Microsoft Edge through browser automation:

1. The message box works without uploading an image.
2. `Show me a volcano and explain it` generated an answer longer than 100 characters and retrieved a real Wikipedia illustration of Augustine volcano. The browser loaded the actual image, with article and image-credit links.
3. The saved conversation and source image reopened after page reload.
4. Desktop and 390-pixel-wide mobile layouts rendered without horizontal overflow.
5. Read aloud invoked the browser's real speech-synthesis API. Audible output and the user's selected system voice were not audited.
6. Browser MediaRecorder captured a test audio device playing the upstream Whisper JFK test recording. Real local Whisper inference transcribed it into the editable message box.
7. The recording was presented for review and was not automatically sent as a chat message.
8. A simulated microphone-permission denial produced the expected visible error.
9. No JavaScript page errors occurred during those checks.

The microphone test used a synthetic browser device, not the user's physical microphone. Physical microphone permissions, recording quality, installed speech voices, and audio output remain dependent on the user's browser and hardware.

## Uploaded-image regression

A real two-cat photo was uploaded through the API. SSDLite detected two cats (scores 0.9480 and 0.6972) and a couch (0.5221). ViLT answered `2` to `How many cats are there?`, at a model score of 88%. The returned explanation contained **214 characters including spaces**, describing the answer, score, and detected labels. Test-created images and completed test conversations were removed after validation.

## Operational notes

- All four local models reached ready status together.
- Already-cached ViLT weights now load without online metadata requests.
- Online article and illustration retrieval requires network access. Connection failures return visible errors.
- New assistant responses are checked against the 100-character minimum before saving. Historical messages are preserved.
- A small local language model can still make factual mistakes; linked Wikipedia references make the learning material inspectable. Internet-image explanations use article context, not direct visual inspection of the retrieved image.
- Desktop and mobile screenshots were inspected locally. They are excluded from the Git repository because their sidebars can contain local upload history.
