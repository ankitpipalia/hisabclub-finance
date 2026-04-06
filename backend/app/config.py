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
    llm_small_model: str = ""
    llm_large_model: str = ""
    llm_runtime_label: str = "shared-local"
    llm_router_enabled: bool = True
    llm_json_mode: bool = True
    llm_vision_enabled: bool = False
    llm_vision_base_url: str = ""
    llm_vision_api_key: str = ""
    llm_vision_model: str = ""
    llm_vision_statement_extraction_enabled: bool = False
    llm_vision_statement_primary: bool = False
    llm_vision_render_dpi: int = 180
    llm_vision_page_limit: int = 24
    llm_prompt_version_statement_extraction: str = "statement_extraction_v2"
    llm_prompt_version_statement_classification: str = "statement_classification_v2"
    llm_iterative_chunk_chars: int = 5200
    llm_iterative_overlap_lines: int = 6
    llm_max_chunk_count: int = 12
    llm_request_timeout_sec: float = 300.0
    llm_request_max_attempts: int = 4
    llm_statement_extract_timeout_sec: float = 300.0
    llm_statement_extract_max_attempts: int = 4
    llm_statement_classify_timeout_sec: float = 180.0
    llm_statement_classify_max_attempts: int = 4
    llm_table_map_timeout_sec: float = 180.0
    llm_table_map_max_attempts: int = 4
    promotion_confidence_threshold: float = 0.75
    min_yield_rate_for_auto_promotion: float = 0.55
    require_cc_integrity_ok_for_auto_promotion: bool = False
    category_web_lookup_enabled: bool = False
    category_web_lookup_timeout_sec: float = 5.0

    # OCR / vision extraction
    ocr_enabled: bool = False
    ocr_base_url: str = "http://localhost:8095/v1"
    ocr_api_key: str = ""
    ocr_model: str = "glm-4.1v-9b-thinking"
    ocr_render_dpi: int = 200
    ocr_page_limit: int = 24
    ocr_min_text_chars_per_page: int = 60
    ocr_min_alpha_ratio: float = 0.15
    ocr_timeout_sec: float = 300.0
    ocr_max_attempts: int = 2

    # Privacy and local processing guardrails
    local_only_mode: bool = True
    local_allowed_roots: str = (
        "/app/uploads,/home,/Users,/Volumes,/mnt,/media,"
        "/home/ankit/Documents,/home/ankit/Downloads"
    )
    local_allowed_llm_hosts: str = "localhost,127.0.0.1,::1"
    cold_storage_enabled: bool = True
    cold_storage_dir: str = "./uploads/cold"

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

    def llm_vision_base_url_resolved(self) -> str:
        return self.llm_vision_base_url.strip() or self.llm_base_url

    def llm_vision_api_key_resolved(self) -> str:
        return self.llm_vision_api_key.strip() or self.llm_api_key

    def llm_vision_model_resolved(self) -> str:
        return self.llm_vision_model.strip() or self.llm_model


settings = Settings()
