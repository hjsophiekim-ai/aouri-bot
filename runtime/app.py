from runtime.api.server import run_server


def main() -> None:
    run_server(host="127.0.0.1", port=8787)


if __name__ == "__main__":
    main()

