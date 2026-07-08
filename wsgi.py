"""WSGI entry point. Used by `flask` CLI and by launcher.py / waitress."""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
