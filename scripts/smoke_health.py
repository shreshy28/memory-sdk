import json
import os
import time
import urllib.error
import urllib.request


def await_ready(name: str, url: str, timeout_seconds: float = 60.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                body = json.load(response)
                if response.status == 200 and body.get("status") == "ready":
                    print(f"{name}: ready")
                    return
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
            last_error = error
        time.sleep(1)
    raise RuntimeError(f"{name} did not become ready at {url}: {last_error}")


if __name__ == "__main__":
    await_ready("api", os.getenv("MEMORY_API_READY_URL", "http://localhost:8000/health/ready"))
    await_ready(
        "worker", os.getenv("MEMORY_WORKER_READY_URL", "http://localhost:8001/health/ready")
    )
