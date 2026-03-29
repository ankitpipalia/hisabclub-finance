from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    app_name: str = "HisabClub"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8356

    # Database
    database_url: str = "postgresql+asyncpg://hisabclub:hisabclub_dev@localhost:6543/hisabclub"
    database_url_sync: str = "postgresql://hisabclub:hisabclub_dev@localhost:6543/hisabclub"
    db_set_role_on_connect: bool = True
    db_rls_role: str = "hisabclub_rls"

    # Redis
    redis_url: str = "redis://localhost:6769/0"
    job_runner_enabled: bool = True
    job_runner_poll_seconds: float = 1.0
    job_runner_dlq_retry_enabled: bool = True

    # Auth
    secret_key: str = "change-me-to-a-random-secret-key-in-production"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30

    # File Storage
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 50
    max_pdf_pages: int = 200

    # LLM
    llm_enabled: bool = False
    llm_base_url: str = "http://localhost:8472/v1"
    llm_api_key: str = ""
    llm_model: str = "Qwen3.5-27B-Q3_K_M.gguf"
    category_web_lookup_enabled: bool = False
    category_web_lookup_timeout_sec: float = 5.0

    # Privacy and local processing guardrails
    local_only_mode: bool = True
    local_allowed_roots: str = "/app/uploads,/home/ankit/Documents,/home/ankit/Downloads"
    local_allowed_llm_hosts: str = "localhost,127.0.0.1,::1"

    # Gmail Integration
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_redirect_uri: str = "https://hisabclub-dev-api.ankit-tech.store/api/v1/gmail/callback"
    data_encryption_key: str = ""

    # Password reset / outbound email
    web_base_url: str = "https://hisabclub-dev-web.ankit-tech.store"
    password_reset_token_expire_minutes: int = 30
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "HisabClub"
    smtp_use_starttls: bool = True
    smtp_use_ssl: bool = False

    model_config = {"env_file": "../.env", "env_file_encoding": "utf-8", "extra": "ignore"}

    def parsed_local_roots(self) -> list[str]:
        return [p.strip() for p in self.local_allowed_roots.split(",") if p.strip()]

    def parsed_local_llm_hosts(self) -> set[str]:
        return {h.strip().lower() for h in self.local_allowed_llm_hosts.split(",") if h.strip()}


settings = Settings()
