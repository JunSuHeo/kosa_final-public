from pathlib import Path
from functools import lru_cache
from urllib.parse import urlsplit
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env", extra="ignore", hide_input_in_errors=True
    )
    app_env: str = "local"
    database_url: str = "postgresql://studio:studio@localhost:54331/studio"
    auth_mode: str = "mock"
    ai_mode: str = "mock"
    llm_provider: str = "openrouter"
    llm_model: str = ""
    openrouter_model: str = "openai/gpt-6.1-sol"
    openai_model: str = "gpt-6.1-sol"
    openrouter_api_key: str = ""
    openai_api_key: str = ""
    llm_api_key: str = ""
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_jwt_audience: str = "authenticated"
    llm_timeout_seconds: int = 240
    local_repository_root: str = ""
    github_local_token: str = ""
    github_user_tokens: dict[str, str] = {}
    local_screen_previews: dict[str, dict[str, str]] = {}

    @model_validator(mode="after")
    def valid_modes(self):
        if self.auth_mode not in {"mock", "supabase"} or self.ai_mode not in {
            "mock",
            "live",
        }:
            raise ValueError("AUTH_MODE / AI_MODE 값이 올바르지 않습니다.")
        if self.app_env != "local" and (
            self.auth_mode == "mock" or self.ai_mode == "mock"
        ):
            raise ValueError("mock 모드는 APP_ENV=local에서만 사용할 수 있습니다.")
        for previews in self.local_screen_previews.values():
            for url in previews.values():
                parsed = urlsplit(url)
                if (self.app_env != "local" or parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"}
                        or parsed.username is not None or parsed.password is not None or not parsed.port):
                    raise ValueError("화면 미리보기에는 로컬 HTTP 주소가 필요합니다.")
        if self.llm_provider not in {"openai", "openrouter"}:
            raise ValueError("지원하지 않는 LLM_PROVIDER입니다.")
        if self.ai_mode == "live" and not self.api_key:
            raise ValueError("live 모드에는 공급자의 서버 API 키가 필요합니다.")
        if self.auth_mode == "supabase" and not self.supabase_url:
            raise ValueError("Supabase URL이 필요합니다.")
        return self

    @property
    def local_repository_root_resolved(self):
        return Path(self.local_repository_root).resolve()

    @property
    def model(self):
        return self.llm_model or (
            self.openrouter_model
            if self.llm_provider == "openrouter"
            else self.openai_model
        )

    @property
    def api_key(self):
        return self.llm_api_key or (
            self.openrouter_api_key
            if self.llm_provider == "openrouter"
            else self.openai_api_key
        )


@lru_cache
def settings():
    return Settings()
