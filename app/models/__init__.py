"""
ORM model registry — import ALL models here so Alembic autogenerate can detect them.

Import order matters: models with FK dependencies must be imported after their targets.
"""

from app.models.base import Base  # noqa: F401

# 1. Core (no FK deps on other app tables)
from app.models.org import Organization, ProjectVisibility, User  # noqa: F401
from app.models.saved_filter import SavedFilter  # noqa: F401

# 2. Opportunities (unified investment target — renamed from ScrapedListing)
from app.models.opportunity import (  # noqa: F401
    Opportunity,
    OpportunityCategory,
    OpportunitySource,
    OpportunityStatus,
)
from app.models.project import PermitStub, Project  # noqa: F401

# 3. Parcels (FK → Opportunity)
from app.models.parcel import (  # noqa: F401
    Parcel,
    ParcelTransformation,
)

# 4. Listing identity / broker models
from app.models.broker import Broker, BrokerDisciplinaryAction, Brokerage  # noqa: F401
from app.models.scraped_listing import ScrapedListing  # noqa: F401  (alias for Opportunity)

# 5. Deals (top-level entity, FK → Organization, User)
#    + Scenarios (financial plan for a Deal, FK → Deal)
#    + Project-level line-item models (FK → Project)
from app.models.deal import (  # noqa: F401
    Deal,
    DealModel,       # backward-compat alias for Scenario
    DealOpportunity,  # stub — removed in migration 0067; kept for import compat
    IncomeStream,
    OperatingExpenseLine,
    OperationalInputs,
    Scenario,        # financial plan (was DealModel / the old deals table)
    UnitMix,         # stub — removed in migration 0067; kept for import compat
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

# 8b. Async export jobs (FK → Scenario, User)
from app.models.export_job import ExportJob, ExportJobStatus  # noqa: F401

# 9. Sensitivity analysis (FK → Opportunity, Scenario, User)
from app.models.scenario import (  # noqa: F401
    ScenarioResult,    # backward-compat alias for SensitivityResult
    Sensitivity,
    SensitivityResult,
    SensitivityStatus,
)

# 10. Portfolio (FK → Organization, Opportunity, Scenario)
from app.models.portfolio import GanttEntry, Portfolio, PortfolioProject  # noqa: F401

# 11. Ingestion (FK → User; Opportunity already imported above)
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
    # Opportunity (unified investment target)
    "Opportunity",
    "OpportunityCategory",
    "OpportunitySource",
    "OpportunityStatus",
    "Project",
    "PermitStub",
    "ScrapedListing",    # alias for Opportunity
    # Parcel
    "Parcel",
    "ParcelTransformation",
    # Brokers
    "Brokerage",
    "Broker",
    "BrokerDisciplinaryAction",
    # Deal (top-level entity) + Scenario (financial plan)
    "Deal",
    "DealOpportunity",   # stub — removed in 0067
    "Scenario",
    "DealModel",
    "OperationalInputs",
    "IncomeStream",
    "OperatingExpenseLine",
    "UnitMix",           # stub — removed in 0067
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
    # Async export jobs
    "ExportJob",
    "ExportJobStatus",
    # Sensitivity analysis
    "Sensitivity",
    "SensitivityResult",
    "SensitivityStatus",
    "ScenarioResult",
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
