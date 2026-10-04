"""Local, single-user Nexa Mind server."""
import os

from nexa_mind import create_app

app = create_app()

if __name__ == "__main__":
    from waitress import serve

    app.extensions["vision"].start()
    app.extensions["conversation"].start()
    port = int(os.environ.get("NEXA_PORT", "5000"))
    print(f"Nexa Mind: http://127.0.0.1:{port}", flush=True)
    serve(app, host="127.0.0.1", port=port, threads=4)
