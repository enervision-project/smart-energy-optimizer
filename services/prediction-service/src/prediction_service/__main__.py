import uvicorn

from prediction_service.settings import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "prediction_service.main:app", host=settings.host, port=settings.port, log_level="info"
    )


if __name__ == "__main__":
    main()
