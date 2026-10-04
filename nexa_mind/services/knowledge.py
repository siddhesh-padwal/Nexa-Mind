"""Live, attributed Wikipedia topic and illustration retrieval. No API key."""
import re
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class KnowledgeUnavailable(RuntimeError):
    pass


def learning_topic(question, previous_topic=""):
    text = question.strip().rstrip("?.!")
    patterns = [
        r"^(?:please\s+)?(?:i\s+(?:want|would like)\s+to\s+)?(?:learn|know)\s+about\s+(.+)",
        r"^(?:please\s+)?(?:teach|tell)\s+me\s+(?:more\s+)?about\s+(.+)",
        r"^(?:please\s+)?(?:show\s+me|i\s+(?:want|would like)\s+to\s+see)\s+(?:(?:an?\s+)?(?:image|picture|photo)\s+of\s+)?(.+)",
        r"^(?:please\s+)?(?:find|search\s+for)\s+(?:(?:an?\s+)?(?:image|picture|photo)\s+of\s+)?(.+)",
        r"^(?:please\s+)?explain\s+(?!more\b|it\b|this\b|that\b)(.+)",
        r"^what\s+(?:is|are)\s+(?!in\b|this\b|that\b|it\b|the\s+(?:color|colour|object|picture|image)\b)(.+)",
    ]
    for pattern in patterns:
        match = re.match(pattern, text, re.I)
        if match:
            topic = re.sub(r"^(?:an?|the)\s+", "", match.group(1), flags=re.I)
            topic = re.sub(r"\s+(?:please|and\s+explain(?:\s+it)?|in\s+(?:simple\s+)?(?:detail|words))$", "", topic, flags=re.I)
            if topic.lower() in {"it", "this", "that", "more", "an image", "a picture", "a photo", "image", "picture"}:
                return previous_topic
            return topic[:160]
    return ""


class KnowledgeService:
    endpoint = "https://en.wikipedia.org/w/api.php"

    def search(self, topic):
        try:
            session = requests.Session()
            session.mount('https://', HTTPAdapter(max_retries=Retry(total=2, connect=1, read=1, status=1,
                          backoff_factor=0.4, status_forcelist=[429, 502, 503, 504], allowed_methods=['GET'])))
            response = session.get(self.endpoint, params={
                "action": "query", "format": "json", "formatversion": 2,
                "generator": "search", "gsrsearch": topic, "gsrlimit": 4, "gsrnamespace": 0,
                "prop": "extracts|pageimages|info|pageprops", "inprop": "url", "ppprop": "disambiguation",
                "exintro": 1, "explaintext": 1, "exchars": 2600,
                "piprop": "thumbnail|name", "pithumbsize": 800,
            }, headers={"User-Agent": "NexaMind/1.1 (local educational application; Wikipedia topic lookup)"}, timeout=(5, 15))
            response.raise_for_status()
            payload = response.json()
            session.close()
        except (requests.RequestException, ValueError) as exc:
            raise KnowledgeUnavailable("Wikipedia could not be reached. Check your internet connection and try again.") from exc
        pages = sorted(payload.get("query", {}).get("pages", []), key=lambda page: page.get("index", 99))
        for page in pages:
            if "disambiguation" in page.get("pageprops", {}) or len(page.get("extract", "")) < 100:
                continue
            image = page.get("thumbnail", {}).get("source", "")
            if image and (urlparse(image).scheme != "https" or urlparse(image).hostname not in {"upload.wikimedia.org", "thumb.wikimedia.org"}):
                image = ""
            source_url = page.get("fullurl", "")
            if urlparse(source_url).scheme != "https" or urlparse(source_url).hostname != "en.wikipedia.org":
                continue
            return {"title": page["title"], "url": source_url, "extract": page["extract"],
                    "image_url": image, "image_title": page.get("pageimage", ""),
                    "image_page": "https://en.wikipedia.org/wiki/File:" + requests.utils.quote(page.get("pageimage", "")),
                    "provider": "Wikipedia", "query": topic,
                    "image_note": "Wikipedia's illustration for this topic. Open image credits for author and licensing information."}
        raise KnowledgeUnavailable("No reliable matching Wikipedia article was found. Try a more specific topic or spelling.")
