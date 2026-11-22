from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    app_env: Literal["local", "test", "production"] = "local"
    auth_mode: Literal["local", "cognito"] = "local"
    database_url: str = "postgresql+psycopg://bolmava:bolmava@localhost:5432/bolmava"
    local_auth_secret: str = "local-demo-secret-change-me"
    cors_origins: list[str] = ["http://localhost:3000"]

    @model_validator(mode="after")
    def fail_closed(self):
        if self.auth_mode == "local" and self.app_env == "production":
            raise ValueError("AUTH_MODE=local is not allowed when APP_ENV=production")
        if self.auth_mode == "cognito":
            # shortcut: Cognito verification is not built yet; refuse to start rather than accept unverified tokens.
            raise ValueError("AUTH_MODE=cognito is not implemented yet")
        return self


settings = Settings()
