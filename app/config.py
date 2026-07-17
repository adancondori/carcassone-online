from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Carcassonne Scoreboard"
    database_url: str = "sqlite:///data/carcassonne.db"

    # Voice (plan v2): faster-whisper runs locally inside the container.
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute: str = "int8"
    voice_language: str = "es"

    model_config = {"env_file": ".env"}


settings = Settings()
