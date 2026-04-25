"""
ORM model registry — import ALL models here so Alembic autogenerate can detect them.

Import order matters: models with FK dependencies must be imported after their targets.
"""

from app.models.base import Base  # noqa: F401

# 1. Core (no FK deps on other app tables)
from app.models.org import Organization, ProjectVisibility, User  # noqa: F401
from app.models.saved_filter import SavedFilter  # noqa: F401

# 2. Opportunities (was Projects — FK → Organization, User)
from app.models.project import Opportunity, PermitStub, Project  # noqa: F401

# 3. Parcels (FK → Opportunity)
from app.models.parcel import (  # noqa: F401
    Parcel,
    ParcelTransformation,
    ProjectParcel,
)

# 4. Listing identity / promotion models
from app.models.broker import Broker, Brokerage  # noqa: F401
from app.models.property import Building, Property  # noqa: F401
from app.models.scraped_listing import ScrapedListing  # noqa: F401

# 5. Deals (top-level entity, FK → Organization, User)
#    + Scenarios (financial plan for a Deal, FK → Deal)
#    + Project-level line-item models (FK → Project)
from app.models.deal import (  # noqa: F401
    Deal,
    DealModel,       # backward-compat alias for Scenario
    DealOpportunity,
    IncomeStream,
    OperatingExpenseLine,
    OperationalInputs,
    Scenario,        # financial plan (was DealModel / the old deals table)
    UseLine,
)

# 6. Capital (FK → Scenario)
from app.models.capital import (  # noqa: F401
    CapitalModule,
    DrawSource,
    WaterfallResult,
    WaterfallTier,
)

# 7. Cash flows (FK → Scenario, IncomeStream)
from app.models.cashflow import (  # noqa: F401
    CashFlow,
    CashFlowLineItem,
    OperationalOutputs,
)

# 8. Workflow manifests (FK → Scenario)
from app.models.manifest import WorkflowRunManifest  # noqa: F401

# 9. Sensitivity analysis (FK → Opportunity, Scenario, User)
#    Previously named Scenario/ScenarioResult — renamed to free up the table name
from app.models.scenario import (  # noqa: F401
    ScenarioResult,    # backward-compat alias for SensitivityResult
    Sensitivity,
    SensitivityResult,
    SensitivityStatus,
)

# 10. Portfolio (FK → Organization, Opportunity, Scenario)
from app.models.portfolio import GanttEntry, Portfolio, PortfolioProject  # noqa: F401

# 11. Ingestion (FK → User; ScrapedListing already imported above)
from app.models.ingestion import (  # noqa: F401
    DedupCandidate,
    IngestJob,
    SavedSearchCriteria,
)

# 12. Milestones (FK → Opportunity, Project)
from app.models.milestone import Milestone  # noqa: F401

# 13. Realie usage tracking (no FK deps)
from app.models.realie_usage import RealieUsage  # noqa: F401

# 14. LoopNet scraper support: API call tracking, snapshot history, conflict log
from app.models.api_call_log import ApiCallLog  # noqa: F401
from app.models.field_conflict_log import FieldConflictAction, FieldConflictLog  # noqa: F401
from app.models.listing_snapshot import ListingSnapshot  # noqa: F401

__all__ = [
    "Base",
    # Org
    "Organization",
    "User",
    "ProjectVisibility",
    # Opportunity (was Project)
    "Opportunity",
    "Project",           # post-acquisition dev effort
    "PermitStub",
    "ScrapedListing",
    # Parcel
    "Parcel",
    "ProjectParcel",
    "ParcelTransformation",
    # Brokers / building promotion
    "Brokerage",
    "Broker",
    "Building",
    "Property",          # backward-compat alias for Building
    # Deal (top-level entity) + Scenario (financial plan)
    "Deal",
    "DealOpportunity",
    "Scenario",          # financial plan (was DealModel)
    "DealModel",         # backward-compat alias for Scenario
    "OperationalInputs",
    "IncomeStream",
    "OperatingExpenseLine",
    "UseLine",
    # Capital
    "CapitalModule",
    "DrawSource",
    "WaterfallTier",
    "WaterfallResult",
    # Cash flow
    "CashFlow",
    "CashFlowLineItem",
    "OperationalOutputs",
    "WorkflowRunManifest",
    # Sensitivity analysis (was Scenario/ScenarioResult)
    "Sensitivity",
    "SensitivityResult",
    "SensitivityStatus",
    "ScenarioResult",    # backward-compat alias
    # Portfolio
    "Portfolio",
    "PortfolioProject",
    "GanttEntry",
    # Milestones
    "Milestone",
    # Ingestion
    "IngestJob",
    "DedupCandidate",
    "SavedSearchCriteria",
    # Realie usage
    "RealieUsage",
    # LoopNet scraper support
    "ApiCallLog",
    "ListingSnapshot",
    "FieldConflictLog",
    "FieldConflictAction",
]
