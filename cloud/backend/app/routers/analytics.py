"""
统计分析路由：数据上报、总览、趋势、模块使用排名。
"""
from datetime import date, timedelta
from collections import defaultdict
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_role
from ..models.analytics import Analytics
from ..models.organization import Organization
from ..schemas.analytics import (
    AnalyticsReport, AnalyticsRead,
    OverviewResponse, OrgSummary,
    TrendsResponse, TrendPoint,
    ModulesResponse, ModuleUsageItem,
)

router = APIRouter(prefix="/api/cloud/analytics", tags=["统计分析"])


@router.post("/report", response_model=AnalyticsRead, status_code=status.HTTP_201_CREATED)
def report_analytics(body: AnalyticsReport, db: Session = Depends(get_db)):
    """Local_Client 上报使用数据（追加模式）。"""
    record = Analytics(
        license_id=body.license_id,
        org_id=body.org_id,
        report_date=body.report_date,
        active_user_count=body.active_user_count,
        experiment_count=body.experiment_count,
        module_usage=body.module_usage,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/overview", response_model=OverviewResponse)
def analytics_overview(
    db: Session = Depends(get_db),
    _=Depends(require_role("super_admin")),
):
    cutoff = date.today() - timedelta(days=30)

    total_active_orgs = db.query(sa_func.count(sa_func.distinct(Analytics.org_id))).filter(
        Analytics.report_date >= cutoff
    ).scalar() or 0

    active_users = db.query(sa_func.sum(Analytics.active_user_count)).filter(
        Analytics.report_date >= cutoff
    ).scalar() or 0

    total_experiments = db.query(sa_func.sum(Analytics.experiment_count)).scalar() or 0

    # 按机构汇总
    rows = (
        db.query(
            Analytics.org_id,
            sa_func.sum(Analytics.active_user_count).label("active_users"),
            sa_func.sum(Analytics.experiment_count).label("experiment_count"),
            sa_func.max(Analytics.report_date).label("last_active"),
        )
        .group_by(Analytics.org_id)
        .order_by(sa_func.sum(Analytics.experiment_count).desc())
        .all()
    )
    summaries = []
    for r in rows:
        org = db.query(Organization).filter(Organization.id == r.org_id).first()
        summaries.append(OrgSummary(
            org_id=r.org_id,
            org_name=org.name if org else "未知",
            active_users=r.active_users or 0,
            experiment_count=r.experiment_count or 0,
            last_active=r.last_active,
        ))

    return OverviewResponse(
        total_active_orgs=total_active_orgs,
        active_users_last_30d=active_users,
        total_experiments=total_experiments,
        org_summaries=summaries,
    )


@router.get("/trends", response_model=TrendsResponse)
def analytics_trends(
    start: date = Query(...),
    end: date = Query(...),
    db: Session = Depends(get_db),
    _=Depends(require_role("super_admin")),
):
    rows = (
        db.query(
            Analytics.report_date,
            sa_func.sum(Analytics.active_user_count).label("active_users"),
            sa_func.sum(Analytics.experiment_count).label("experiment_count"),
        )
        .filter(Analytics.report_date >= start, Analytics.report_date <= end)
        .group_by(Analytics.report_date)
        .order_by(Analytics.report_date)
        .all()
    )
    return TrendsResponse(data=[
        TrendPoint(report_date=r.report_date, active_users=r.active_users or 0, experiment_count=r.experiment_count or 0)
        for r in rows
    ])


@router.get("/modules", response_model=ModulesResponse)
def analytics_modules(
    db: Session = Depends(get_db),
    _=Depends(require_role("super_admin")),
):
    records = db.query(Analytics).filter(Analytics.module_usage.isnot(None)).all()
    totals: dict[str, int] = defaultdict(int)
    for rec in records:
        if isinstance(rec.module_usage, dict):
            for mod, cnt in rec.module_usage.items():
                totals[mod] += cnt
    sorted_items = sorted(totals.items(), key=lambda x: x[1], reverse=True)
    return ModulesResponse(data=[
        ModuleUsageItem(module_id=mod, total_count=cnt) for mod, cnt in sorted_items
    ])
