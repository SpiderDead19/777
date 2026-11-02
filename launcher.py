import os
import sys
import socket
import threading
import time
import webbrowser

from streamlit.web import cli as stcli


def resource_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def wait_and_open(port: int) -> None:
    url = f"http://localhost:{port}"
    for _ in range(80):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                webbrowser.open(url)
                return
        except OSError:
            time.sleep(0.25)


def main() -> None:
    port = 8501
    threading.Thread(target=wait_and_open, args=(port,), daemon=True).start()
    sys.argv = [
        "streamlit",
        "run",
        resource_path("app.py"),
        "--server.headless=true",
        f"--server.port={port}",
        "--browser.gatherUsageStats=false",
    ]
    stcli.main()


if __name__ == "__main__":
    main()
