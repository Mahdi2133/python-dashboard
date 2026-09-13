"""WSGI entry point for the `flask` CLI and any external WSGI server."""
from app import create_app

app = create_app()

if __name__ == "__main__":
    from app.paths import load_config
    cfg = load_config()
    app.run(host=cfg.get("host", "0.0.0.0"), port=int(cfg.get("port", 5050)), debug=True)
