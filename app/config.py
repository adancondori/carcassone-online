from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Carcassonne Scoreboard"
    database_url: str = "sqlite:///data/carcassonne.db"

    model_config = {"env_file": ".env"}


settings = Settings()
