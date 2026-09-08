from runtime.ai.dotenv import ensure_dotenv_loaded
from runtime.api.server import run_server


def main() -> None:
    # Load the canonical .env BEFORE anything reads os.environ, so the server
    # behaves identically no matter which directory it was launched from.
    ensure_dotenv_loaded()
    run_server(host="127.0.0.1", port=8787)


if __name__ == "__main__":
    main()
