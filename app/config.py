"""Application settings — reads from environment / .env file."""

from uuid import UUID

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

    # Crexi fetch path. Default OFF: scrape Crexi's API directly from the app host.
    # The legacy residential proxy (ProxyOn) is gone/expired and returns CONNECT 403,
    # which silently failed every nightly run. Direct fetch from VM 114 works for our
    # low volume (Portland+Gresham, ~100 listings, once daily). Flip to True only if a
    # working residential proxy is reconfigured AND Crexi starts blocking the host IP.
    crexi_use_proxy: bool = False

    # Crexi listing lifecycle — auto-archive de-listed listings.
    # A Crexi opportunity not re-seen in `stale_days` (or whose source status
    # says sold/off-market) is archived (data kept, hidden from active views).
    # Guard: only runs when the scraper itself was seen within `health_days`,
    # so a stalled scraper can't wrongly archive the whole live inventory.
    crexi_archive_stale_days: int = 21
    crexi_archive_scraper_health_days: int = 3

    # Test-deal janitor — daily purge of accumulated E2E / regression test deals
    # (anything the Hide-Test filter hides). Age guard: only sweep deals older
    # than this many hours, so an in-flight test run's fresh deal is never deleted
    # mid-run. See app/services/test_cleanup.py + app/tasks/maintenance.py.
    test_deal_purge_min_age_hours: int = 6

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
    # Explicit org to assign inbound emails to. Set in .env for multi-org deployments.
    # If unset, the webhook falls back to the single org in the DB and fails hard if
    # multiple orgs exist (prevents silent cross-tenant assignment).
    inbound_email_org_id: UUID | None = None

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
    # Document room (per-project file storage)
    # -------------------------------------------------------------------------
    # Master flag for the document-room module (nav entry + routes). Off-switch
    # for a clean rollback without code changes.
    documents_module_enabled: bool = True
    # Filesystem root for uploaded document bytes. Lives under the existing
    # ./data:/app/data Docker volume. Metadata stays in Postgres.
    document_storage_path: str = "/app/data/doc_room"
    # Per-file upload ceiling (bytes). 50 MB covers leases / rent rolls / plans.
    document_max_size_bytes: int = 50 * 1024 * 1024
    # Comma-separated allowed file extensions (lowercase, dot-prefixed).
    document_allowed_extensions: str = ".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png"
    # Gotenberg service for Office→PDF preview conversion (Phase 1b).
    gotenberg_url: str = "http://gotenberg:3000"
    # External share-link lifetime (Phase 3). 30 days default.
    doc_share_token_max_age_seconds: int = 60 * 60 * 24 * 30

    @property
    def document_allowed_extensions_set(self) -> set[str]:
        """Parse document_allowed_extensions into a lowercase set of extensions."""
        return {
            e.strip().lower()
            for e in self.document_allowed_extensions.split(",")
            if e.strip()
        }

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
