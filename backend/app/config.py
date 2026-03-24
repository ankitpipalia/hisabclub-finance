from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    app_name: str = "HisabClub"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    database_url: str = "postgresql+asyncpg://hisabclub:hisabclub_dev@localhost:5432/hisabclub"
    database_url_sync: str = "postgresql://hisabclub:hisabclub_dev@localhost:5432/hisabclub"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    secret_key: str = "change-me-to-a-random-secret-key-in-production"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30

    # File Storage
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 50

    # LLM
    llm_enabled: bool = False
    llm_base_url: str = "http://localhost:8080/v1"
    llm_api_key: str = ""
    llm_model: str = "qwq-32b"
    category_web_lookup_enabled: bool = False
    category_web_lookup_timeout_sec: float = 5.0

    # Privacy and local processing guardrails
    local_only_mode: bool = True
    local_allowed_roots: str = "/home/ankit/Documents"
    local_allowed_llm_hosts: str = "localhost,127.0.0.1,::1"

    # Gmail Integration
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_redirect_uri: str = "http://localhost:8000/api/v1/gmail/callback"

    model_config = {"env_file": "../.env", "env_file_encoding": "utf-8", "extra": "ignore"}

    def parsed_local_roots(self) -> list[str]:
        return [p.strip() for p in self.local_allowed_roots.split(",") if p.strip()]

    def parsed_local_llm_hosts(self) -> set[str]:
        return {h.strip().lower() for h in self.local_allowed_llm_hosts.split(",") if h.strip()}


settings = Settings()
