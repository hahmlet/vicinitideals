"""Application settings — reads from environment / .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Database
    # -------------------------------------------------------------------------
    database_url: str = (
        "postgresql+asyncpg://vicinitideals:changeme@postgres:5432/vicinitideals"
    )
    postgres_password: str = "changeme"

    # -------------------------------------------------------------------------
    # Redis / Celery
    # -------------------------------------------------------------------------
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # -------------------------------------------------------------------------
    # API security
    # -------------------------------------------------------------------------
    vicinitideals_api_key: str = "changeme-generate-with-openssl-rand-hex-32"
    secret_key: str = "changeme-generate-with-openssl-rand-hex-32"

    # -------------------------------------------------------------------------
    # Transactional email (Resend — https://resend.com)
    # -------------------------------------------------------------------------
    # Leave resend_api_key empty to disable email sending entirely
    # (register/reset still work but no email goes out — useful for local dev).
    resend_api_key: str = ""
    email_from: str = "auth@viciniti.deals"
    email_from_name: str = "Viciniti Deals"
    # Base URL used when building links inside email bodies (verify / reset).
    # Must match the public-facing domain (viciniti.deals in prod, localhost in dev).
    app_base_url: str = "https://viciniti.deals"
    # Token lifetimes
    email_verify_token_max_age_seconds: int = 60 * 60 * 24  # 24 hours
    password_reset_token_max_age_seconds: int = 60 * 30      # 30 minutes
    invite_token_max_age_seconds: int = 60 * 60 * 24 * 7    # 7 days

    # -------------------------------------------------------------------------
    # Billing (Stripe)
    # -------------------------------------------------------------------------
    # Set stripe_secret_key to enable the Settings > Billing Stripe flow.
    # Use test keys first (sk_test_...) to validate with Stripe test cards.
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_price_pro_monthly: str = ""
    stripe_price_pro_annual: str = ""
    stripe_trial_days: int = 30

    # -------------------------------------------------------------------------
    # Error monitoring (BugSink — Sentry-SDK compatible)
    # -------------------------------------------------------------------------
    sentry_dsn: str | None = None
    environment: str = "production"

    # -------------------------------------------------------------------------
    # Scraper (Stage 1C)
    # -------------------------------------------------------------------------
    lxc134_scrapling_url: str = "http://192.168.1.134:8191"
    scrape_interval_hours: int = 6

    # ProxyOn residential proxies (proxyon.io) — used for Crexi/LoopNet scraping
    proxyon_residential_host: str = "residential.proxyon.io"
    proxyon_residential_port: int = 1111
    proxyon_residential_username: str = ""
    proxyon_residential_password: str = ""
    proxyon_api_key: str = ""

    # ProxyOn datacenter proxies — round-robin pool for GIS enrichment + cache downloads
    # Comma-separated list of http://user:pass@host:port URLs (plain str to avoid JSON decode)
    proxyon_datacenter_proxies: str = ""

    # Crexi authenticated account (dummy account for Portland pagination bypass)
    crexi_username: str = ""
    crexi_password: str = ""

    # -------------------------------------------------------------------------
    # Realie.ai property data enrichment (https://realie.ai)
    # Free tier: 25 calls/month. Hard lock enforced in RealieEnricher.
    # -------------------------------------------------------------------------
    realie_api_key: str = ""

    # -------------------------------------------------------------------------
    # Market polygons — target-market clipping for the Crexi scraper.
    # JSON of active polygons; listings outside them are dropped on ingest.
    # -------------------------------------------------------------------------
    # rapidapi_key is retained: still surfaced by the ingest-status UI.
    rapidapi_key: str = ""
    market_polygons_path: str = "app/data/market_polygons.json"

    # -------------------------------------------------------------------------
    # Pro forma import — local LLM via Ollama
    # -------------------------------------------------------------------------
    # Base URL for the Ollama API (OpenAI-compatible). Defaults to the ollama
    # Docker service on VM 114. Override in .env if running Ollama separately.
    ollama_base_url: str = "http://ollama:11434/v1"
    # Model used for pro forma parsing. qwen2.5:7b or llama3.1:8b both work.
    ollama_model: str = "qwen2.5:7b"

    # -------------------------------------------------------------------------
    # Email ingest webhook
    # -------------------------------------------------------------------------
    # Shared secret sent by the Cloudflare Email Worker in X-Email-Ingest-Secret header.
    # Generate with: openssl rand -hex 32
    # Resend inbound webhook signing secret (from Resend dashboard, Svix format: whsec_...)
    resend_webhook_secret: str = ""

    # -------------------------------------------------------------------------
    # Financial model defaults
    # -------------------------------------------------------------------------
    # Risk-free rate (10Y Treasury) used in the Spread Stack export KPIs.
    # Applied when scenario.risk_free_rate_pct is NULL. Override per-deal
    # in scenario settings when the rate environment shifts significantly.
    default_risk_free_rate_pct: float = 4.25

    # -------------------------------------------------------------------------
    # Multi-tenant access control
    # -------------------------------------------------------------------------
    # When True, list endpoints (deals, opportunities, etc.) are scoped to the
    # signed-in user's organization. Set to False only for single-tenant
    # deployments or debugging cross-org visibility issues.
    org_isolation_enabled: bool = True

    # -------------------------------------------------------------------------
    # Alembic / migrations
    # -------------------------------------------------------------------------
    # Sync DSN used only by Alembic CLI (asyncpg cannot be used synchronously)
    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace(
            "postgresql+asyncpg://", "postgresql+psycopg2://"
        )


settings = Settings()
