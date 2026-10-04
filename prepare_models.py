"""Download and verify both models before starting the web server."""
import logging
from nexa_mind import create_app

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app = create_app()
    service = app.extensions["vision"]
    print("Preparing local models. The first run needs an internet connection.", flush=True)
    service.wait_ready()
    print(service.status()["detail"], flush=True)
    app.extensions["conversation"].wait_ready()
    print(app.extensions["conversation"].status()["detail"], flush=True)
