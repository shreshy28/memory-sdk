import uvicorn

from memory_worker.app import create_app
from memory_worker.config import get_settings

app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run("memory_worker.main:app", host="0.0.0.0", port=8001, log_level=settings.log_level)
