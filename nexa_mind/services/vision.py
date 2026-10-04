"""Real local inference only. A failed model is never replaced by sample results."""
import logging
import os
import threading
import time

logger = logging.getLogger(__name__)
MODEL_LOAD_LOCK = threading.Lock()
VQA_MODEL = "dandelin/vilt-b32-finetuned-vqa"
VQA_REVISION = "d0a1f6ab88522427a7ae76ceb6e1e1e7b68a1d08"


class ModelUnavailable(RuntimeError):
    pass


class ModelBusy(RuntimeError):
    pass


class VisionService:
    def __init__(self, cache_dir):
        self.cache_dir = cache_dir
        self._state_lock = threading.Lock()
        self._inference_lock = threading.Lock()
        self._loading = False
        self._status = {"state": "not_loaded", "detail": "Models have not been loaded yet.", "detector": False, "vqa": False}

    def status(self):
        with self._state_lock:
            return dict(self._status)

    def _update(self, **fields):
        with self._state_lock:
            self._status.update(fields)

    def start(self):
        with self._state_lock:
            if self._loading or self._status["state"] == "ready":
                return
            self._loading = True
            self._status.update(state="loading", detail="Loading object detector…")
        threading.Thread(target=self._load, daemon=True, name="nexa-model-loader").start()

    def _load(self):
        # Transformers lazy imports are not safe to initialize simultaneously.
        with MODEL_LOAD_LOCK:
            self._load_impl()

    def _load_impl(self):
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
            os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
            os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
            import torch
            from torchvision.models.detection import SSDLite320_MobileNet_V3_Large_Weights, ssdlite320_mobilenet_v3_large
            from transformers import ViltForQuestionAnswering, ViltProcessor

            torch.set_num_threads(max(1, min(4, (os.cpu_count() or 2))))
            torch.hub.set_dir(str(self.cache_dir / "torch"))
            weights = SSDLite320_MobileNet_V3_Large_Weights.COCO_V1
            self.detector = ssdlite320_mobilenet_v3_large(weights=weights, progress=True).eval()
            self.transform = weights.transforms()
            self.labels = weights.meta["categories"]
            self._update(detector=True, detail="Loading visual question model (first download is about 470 MB)…")
            options = {"cache_dir": str(self.cache_dir / "huggingface"), "revision": VQA_REVISION}
            cached_weights = (self.cache_dir / "huggingface" / "models--dandelin--vilt-b32-finetuned-vqa"
                              / "snapshots" / VQA_REVISION / "pytorch_model.bin")
            if cached_weights.is_file():
                options["local_files_only"] = True
            self.processor = ViltProcessor.from_pretrained(VQA_MODEL, **options)
            self.vqa = ViltForQuestionAnswering.from_pretrained(VQA_MODEL, use_safetensors=False, **options).eval()
            self._update(state="ready", vqa=True, detail="Both AI models are ready. Images are processed locally.")
        except Exception:
            logger.exception("Could not load AI models")
            self._update(state="error", detail="Models could not load. Check your connection, free disk space, and server log, then retry.")
        finally:
            with self._state_lock:
                self._loading = False

    def wait_ready(self, timeout=1800):
        self.start()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.status()
            if status["state"] == "ready":
                return
            if status["state"] == "error":
                raise ModelUnavailable(status["detail"])
            time.sleep(0.2)
        raise ModelUnavailable("Model loading timed out.")

    def _acquire(self):
        if self.status()["state"] != "ready":
            raise ModelUnavailable("AI models are not ready yet. Wait for the model status to say Ready.")
        if not self._inference_lock.acquire(blocking=False):
            raise ModelBusy("Nexa Mind is processing another request. Please try again in a moment.")

    def detect(self, image):
        self._acquire()
        try:
            import torch
            with torch.inference_mode():
                output = self.detector([self.transform(image)])[0]
            detections = []
            for box, label, score in zip(output["boxes"].tolist(), output["labels"].tolist(), output["scores"].tolist()):
                if score < 0.25 or self.labels[label] == "N/A":
                    continue
                x1, y1, x2, y2 = box
                detections.append({
                    "label": self.labels[label], "score": round(score, 4),
                    "box": [round(max(0, min(image.width, x1)), 2), round(max(0, min(image.height, y1)), 2),
                            round(max(0, min(image.width, x2)), 2), round(max(0, min(image.height, y2)), 2)],
                })
            return detections
        finally:
            self._inference_lock.release()

    def answer(self, image, question):
        self._acquire()
        try:
            import torch
            tokens = self.processor.tokenizer(question, add_special_tokens=True)["input_ids"]
            if len(tokens) > 40:
                raise ValueError("Please shorten your question to 40 tokens (roughly 25–30 words).")
            inputs = self.processor(image, question, return_tensors="pt")
            with torch.inference_mode():
                scores = self.vqa(**inputs).logits.sigmoid()[0]
            values, indices = scores.topk(3)
            candidates = [{"answer": self.vqa.config.id2label[int(index)], "score": round(float(value), 4)}
                          for value, index in zip(values, indices)]
            return {"answer": candidates[0]["answer"], "score": candidates[0]["score"],
                    "uncertain": candidates[0]["score"] < 0.5, "alternatives": candidates[1:],
                    "model": VQA_MODEL,
                    "note": "Model scores are not calibrated probabilities. Answers can be wrong; verify them against the image."}
        finally:
            self._inference_lock.release()
