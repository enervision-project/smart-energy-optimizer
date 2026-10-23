import uvicorn

from ml_engine.settings import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run("ml_engine.main:app", host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
