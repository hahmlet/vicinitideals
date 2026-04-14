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
    # Alembic / migrations
    # -------------------------------------------------------------------------
    # Sync DSN used only by Alembic CLI (asyncpg cannot be used synchronously)
    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace(
            "postgresql+asyncpg://", "postgresql+psycopg2://"
        )


settings = Settings()
