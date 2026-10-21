from datetime import date, datetime
from typing import Dict, List
from pydantic import BaseModel, ConfigDict


class AnalyticsReport(BaseModel):
    """Local_Client 上报的使用数据"""
    license_id: int
    org_id: int
    report_date: date
    active_user_count: int = 0
    experiment_count: int = 0
    module_usage: Dict[str, int] = {}


class AnalyticsRead(BaseModel):
    id: int
    license_id: int | None
    org_id: int | None
    report_date: date
    active_user_count: int
    experiment_count: int
    module_usage: Dict[str, int] | None

    model_config = ConfigDict(from_attributes=True)


class OrgSummary(BaseModel):
    org_id: int
    org_name: str
    active_users: int
    experiment_count: int
    last_active: date | None


class OverviewResponse(BaseModel):
    total_active_orgs: int
    active_users_last_30d: int
    total_experiments: int
    org_summaries: List[OrgSummary]


class TrendPoint(BaseModel):
    report_date: date
    active_users: int
    experiment_count: int


class TrendsResponse(BaseModel):
    data: List[TrendPoint]


class ModuleUsageItem(BaseModel):
    module_id: str
    total_count: int


class ModulesResponse(BaseModel):
    data: List[ModuleUsageItem]
