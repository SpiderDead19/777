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


def free_port() -> int:
    """Choose an available localhost port so a running app does not block launch."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> None:
    os.environ.setdefault("SNAB_LOCAL_MODE", "1")
    port = free_port()
    threading.Thread(target=wait_and_open, args=(port,), daemon=True).start()
    sys.argv = [
        "streamlit",
        "run",
        resource_path("online_app.py"),
        "--server.headless=true",
        "--server.address=127.0.0.1",
        f"--server.port={port}",
        "--server.fileWatcherType=none",
        "--browser.gatherUsageStats=false",
    ]
    stcli.main()


if __name__ == "__main__":
    main()
