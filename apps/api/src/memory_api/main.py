import uvicorn

from memory_api.app import create_app
from memory_api.config import get_settings

app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run("memory_api.main:app", host="0.0.0.0", port=8000, log_level=settings.log_level)
