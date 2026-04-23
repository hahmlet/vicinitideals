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

    # Gresham parcel lookup (REAL-65)
    gresham_arcgis_mapserver_url: str = "https://gis.greshamoregon.gov/ext/rest/services/Taxlots/MapServer"
    gresham_arcgis_taxlot_layer_id: int = 0
    gresham_arcgis_address_layer_id: int = 0
    gresham_arcgis_timeout_seconds: float = 20.0

    # Clackamas exact-address parcel lookup (REAL-68)
    clackamas_maps_base_url: str = "https://maps.clackamas.us"
    clackamas_maps_timeout_seconds: float = 20.0

    # Oregon City exact-address parcel lookup (REAL-69)
    oregoncity_arcgis_address_url: str = "https://maps.orcity.org/arcgis/rest/services/AddressPts_PUBLIC/MapServer/0/query"
    oregoncity_arcgis_taxlot_url: str = "https://maps.orcity.org/arcgis/rest/services/Taxlots_PUBLIC/MapServer/0/query"
    oregoncity_arcgis_timeout_seconds: float = 20.0

    # Portland exact-address parcel lookup (REAL-67)
    portlandmaps_base_url: str = "https://www.portlandmaps.com/arcgis/rest/services"
    portlandmaps_timeout_seconds: float = 20.0

    # -------------------------------------------------------------------------
    # Realie.ai property data enrichment (https://realie.ai)
    # Free tier: 25 calls/month. Hard lock enforced in RealieEnricher.
    # -------------------------------------------------------------------------
    realie_api_key: str = ""

    # -------------------------------------------------------------------------
    # HelloData.ai market data enrichment (https://hellodata.ai)
    # Pay-per-call: ~$0.50/endpoint. Budget enforced in HelloDataEnricher.
    # hellodata_cost_per_call_cents is configurable in cents (default 50 = $0.50).
    # hellodata_monthly_budget_cents is the dollar cap per calendar month.
    # NOTE: Portland listings are excluded — see CLAUDE.md Market Coverage Policy.
    # -------------------------------------------------------------------------
    hellodata_api_key: str = ""
    hellodata_base_url: str = "https://api.hellodata.ai"
    hellodata_cost_per_call_cents: int = 50
    hellodata_monthly_budget_cents: int = 10000  # $100/mo default ceiling

    # -------------------------------------------------------------------------
    # LoopNet RapidAPI (https://rapidapi.com/asyncsolutions-asyncsolutions-default/api/loopnet-api)
    # Free tier: 100 calls/month. Second tier: 5,000 calls/month.
    # Budget is enforced in app/scrapers/loopnet.py BudgetGuard against api_call_log.
    # -------------------------------------------------------------------------
    rapidapi_key: str = ""
    loopnet_rapidapi_host: str = "loopnet-api.p.rapidapi.com"
    loopnet_polygon_path: str = "app/data/market_polygons.json"
    loopnet_monthly_budget: int = 100
    # Safety margin held in reserve except on the final day of the month.
    loopnet_budget_safety_margin: int = 5
    # Seed experiment: when enabled, the daily refresh task snapshots every
    # captured LoopNet listing to listing_snapshots to empirically characterize
    # update frequency. Self-disables after loopnet_experiment_end_date.
    loopnet_experiment_enabled: bool = False
    loopnet_experiment_end_date: str | None = None  # ISO YYYY-MM-DD

    # Categories that trigger ExtendedDetails fetch in TARGET polygons.
    # Comma-separated. Categories are derived by classify_categories() and
    # include: multifamily, land, mixed_use, retail, office, industrial, flex, other.
    # Comp-only polygons always restrict ED to multifamily regardless of this.
    loopnet_target_ed_categories: str = "multifamily,land,mixed_use"

    # When True, the weekly sweep uses bulkDetails (batches of 20) to pre-classify
    # listings by listingType + subtype BEFORE calling SaleDetails. Cuts API-call
    # volume ~55-60% for high-volume sweeps by skipping SD on listings that
    # obviously don't match our categories.
    loopnet_use_bulk_triage: bool = True

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
