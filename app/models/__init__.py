"""
ORM model registry — import ALL models here so Alembic autogenerate can detect them.

Import order matters: models with FK dependencies must be imported after their targets.
"""

from app.models.base import Base  # noqa: F401

# 1. Core (no FK deps on other app tables)
from app.models.org import MembershipStatus, OrgInvite, Organization, ProjectVisibility, User  # noqa: F401
from app.models.saved_filter import SavedFilter  # noqa: F401

# 2. Opportunities (unified investment target — renamed from ScrapedListing)
from app.models.opportunity import (  # noqa: F401
    Opportunity,
    OpportunityCategory,
    OpportunitySource,
    OpportunityStatus,
)
from app.models.project import PermitStub, Project  # noqa: F401

# 4. Listing identity / broker models
from app.models.broker import Broker, BrokerDisciplinaryAction, Brokerage  # noqa: F401
from app.models.scraped_listing import ScrapedListing  # noqa: F401  (alias for Opportunity)

# 5. Deals (top-level entity, FK → Organization, User)
#    + Scenarios (financial plan for a Deal, FK → Deal)
#    + Project-level line-item models (FK → Project)
from app.models.deal import (  # noqa: F401
    Deal,
    DealOpportunity,  # stub — removed in migration 0067; kept for import compat
    IncomeStream,
    OperatingExpenseLine,
    OperationalInputs,
    Scenario,        # financial plan
    ScenarioSnapshot,
    UnitMix,         # stub — removed in migration 0072; kept for import compat
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

# 7b. Capital draw events (FK → Scenario, Project)
from app.models.capital_draw_event import CapitalDrawEvent, DrawAllocationReason  # noqa: F401

# 8. Workflow manifests (FK → Scenario)
from app.models.manifest import WorkflowRunManifest  # noqa: F401

# 8b. Async export jobs (FK → Scenario, User)
from app.models.export_job import ExportJob, ExportJobStatus  # noqa: F401

# 9. Sensitivity analysis (FK → Opportunity, Scenario, User)
from app.models.scenario import (  # noqa: F401
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

# 14. Field conflict log (dedup merge audit — used by Crexi ingest)
from app.models.field_conflict_log import FieldConflictAction, FieldConflictLog  # noqa: F401
from app.models.map_polygon import MapPolygon  # noqa: F401

# 15. Scenario templates (FK → Organization, User, Scenario)
from app.models.scenario_template import ScenarioTemplate  # noqa: F401
from app.models.settings import OrgSetting, UserSetting  # noqa: F401

# 15. Source Vehicles (FK → Organization, User)
from app.models.source_vehicle import OrgSourceVehicle, SourceVehicle, UserSourceVehicle  # noqa: F401

# 16. Email ingest (FK → Organization, Deal — imported after Deal to respect FK order)
from app.models.email_ingest import (  # noqa: F401
    EmailDealSuggestion,
    InboundEmail,
    InboundEmailStatus,
    SuggestionSourceType,
)

# 17. Document room (FK → Organization, Project, User)
from app.models.document import (  # noqa: F401
    Document,
    DocumentPreviewStatus,
    DocumentStatus,
)

__all__ = [
    "Base",
    # Org
    "Organization",
    "User",
    "ProjectVisibility",
    "MembershipStatus",
    "OrgInvite",
    # Opportunity (unified investment target)
    "Opportunity",
    "OpportunityCategory",
    "OpportunitySource",
    "OpportunityStatus",
    "Project",
    "PermitStub",
    "ScrapedListing",    # alias for Opportunity
    # Brokers
    "Brokerage",
    "Broker",
    "BrokerDisciplinaryAction",
    # Deal (top-level entity) + Scenario (financial plan)
    "Deal",
    "DealOpportunity",   # stub — removed in 0067
    "Scenario",
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
    # Capital draw events
    "CapitalDrawEvent",
    "DrawAllocationReason",
    "WorkflowRunManifest",
    # Async export jobs
    "ExportJob",
    "ExportJobStatus",
    # Sensitivity analysis
    "Sensitivity",
    "SensitivityResult",
    "SensitivityStatus",
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
    # Field conflict log (dedup merge audit)
    "FieldConflictLog",
    "FieldConflictAction",
    # Org & user defaults
    "OrgSetting",
    "UserSetting",
    # Source vehicles
    "SourceVehicle",
    "OrgSourceVehicle",
    "UserSourceVehicle",
    # Email ingest
    "InboundEmail",
    "InboundEmailStatus",
    "EmailDealSuggestion",
    "SuggestionSourceType",
    # Document room
    "Document",
    "DocumentStatus",
    "DocumentPreviewStatus",
]
