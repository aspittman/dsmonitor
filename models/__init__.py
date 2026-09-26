from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class HealthCheck:
    name: str
    status: str
    reason: str


@dataclass
class EngineStatus:
    engine_id: str
    display_name: str
    status: str = 'UNKNOWN'
    infrastructure: bool = False
    availability: str = 'UNKNOWN'
    dependency_status: Optional[str] = None
    monitoring_issue: Optional[str] = None
    last_heartbeat: Optional[str] = None
    last_activity: Optional[str] = None
    last_success: Optional[str] = None
    current_operation: Optional[str] = None
    operations_today: Optional[int] = None
    successes_today: Optional[int] = None
    failures_today: Optional[int] = None
    last_error: Optional[str] = None
    checks: list = field(default_factory=list)
    dependencies: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    service_capabilities: dict = field(default_factory=dict)
    activity: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def dict(self):
        return asdict(self)


@dataclass
class StageStatus:
    stage: str
    engine: str
    status: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    retries: Optional[int] = None
    error: Optional[str] = None
    references: dict = field(default_factory=dict)


@dataclass
class ProcessStatus:
    process_id: str
    process_type: str
    display_name: str
    status: str
    organization_id: Optional[str] = None
    current_stage: Optional[str] = None
    started_at: Optional[str] = None
    last_activity: Optional[str] = None
    completed_at: Optional[str] = None
    error_count: Optional[int] = None
    last_error: Optional[str] = None
    correlation_id: Optional[str] = None
    stages: list = field(default_factory=list)
    source: str = 'dsorchestrator'
    source_status: Optional[str] = None
    reason: Optional[str] = None
    duration_seconds: Optional[float] = None
    lineage: list = field(default_factory=list)
    service_id: Optional[str] = None
    parent_run_id: Optional[str] = None

    def dict(self):
        return asdict(self)
