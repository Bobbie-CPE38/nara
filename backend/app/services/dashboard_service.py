"""
GET /dashboard: one read of what needs attention now (docs/workflow.md 6.31, 9.8).

Round 6 PR F1. Reads only: no flush of new rows, no lock, no commit. Every number is
limited to the wards the demo user sees (`gap_check_service.ward_scope`, R6-Q16 ก).
The gap is measured only for shifts in progress or starting within
DASHBOARD_SHORTAGE_WINDOW_HOURS of the Backend Clock, so the cost of a refresh does
not grow with every shift in the system (about 4.5 ms per shift at demo scale).
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import settings
from app.core.constants import (
    DASHBOARD_MAX_NO_SHOWS,
    DASHBOARD_MAX_SHORTAGES,
    DASHBOARD_SHORTAGE_WINDOW_HOURS,
)
from app.db.models import (
    CandidateOutreach,
    LlmDailyUsage,
    Shift,
    Staff,
    StaffingCase,
    StaffingEvent,
)
from app.domain.enums import AUTOMATION_STOPPED_STATUSES, CaseStatus, EventType, OutreachStatus
from app.schemas.dashboard import (
    CaseStatusCount,
    Dashboard,
    DashboardModes,
    LlmUsage,
    NamedGap,
    NoShowEvent,
    OpenOffers,
    Shortage,
    WardCount,
)
from app.services import approval_service, gap_check_service, llm_gateway
from app.services.gap_check_service import WardScope
from app.services.merge_window_service import NO_SHOW_REASON


def build(db: Session, staff: Staff) -> Dashboard:
    scope = gap_check_service.ward_scope(db, staff)
    now = clock.now()
    with db.no_autoflush:
        return Dashboard(
            now=now,
            modes=DashboardModes(
                line_mode=settings.line_mode,
                llm_provider=settings.llm_provider,
                llm_enabled=settings.llm_enabled,
            ),
            wards=list(scope.ward_ids),
            cases_by_status=_cases_by_status(db, scope),
            shortages=_shortages(db, scope, now),
            pending_approvals=_pending_approvals(db, scope),
            open_offers=OpenOffers(count=_open_offers(db, scope, now)),
            recent_no_show=_recent_no_shows(db, scope),
            llm_usage=_llm_usage(db, now) if settings.llm_enabled else None,
        )


def _cases_by_status(db: Session, scope: WardScope) -> list[CaseStatusCount]:
    counts = {
        status: count
        for status, count in db.execute(
            select(StaffingCase.status, func.count())
            .join(Shift, Shift.id == StaffingCase.shift_id)
            .where(Shift.ward_id.in_(scope.ward_ids))
            .group_by(StaffingCase.status)
        )
    }
    return [CaseStatusCount(status=status, count=counts.get(status, 0)) for status in CaseStatus]


def _shortages(db: Session, scope: WardScope, now: datetime) -> list[Shortage]:
    """Short shifts of the window, earliest first, at most DASHBOARD_MAX_SHORTAGES."""
    shifts = db.scalars(
        select(Shift)
        .where(
            Shift.ward_id.in_(scope.ward_ids),
            Shift.is_active.is_(True),
            Shift.end_at > now,
            Shift.start_at < now + timedelta(hours=DASHBOARD_SHORTAGE_WINDOW_HOURS),
        )
        .order_by(Shift.start_at, Shift.id)
    ).all()
    short = []
    for shift in shifts:
        assessment = gap_check_service.assess_or_none(db, shift)
        if assessment is None:  # no requirement: cannot be measured, so skipped (6.31)
            continue
        result = assessment.result
        if result.has_gap:
            short.append((shift, result))
        if len(short) == DASHBOARD_MAX_SHORTAGES:
            break
    names = gap_check_service.names_of(
        db,
        {role_id for _, result in short for role_id in result.role_gaps},
        {skill_id for _, result in short for skill_id in result.skill_gaps},
    )
    cases = gap_check_service.running_case_ids(db, [shift.id for shift, _ in short])
    return [
        Shortage(
            shift_id=shift.id,
            ward_id=shift.ward_id,
            start_at=shift.start_at,
            end_at=shift.end_at,
            headcount_gap=result.headcount_gap,
            role_gaps=[
                NamedGap(name=names.roles[role_id], gap_count=count.gap_count)
                for role_id, count in sorted(result.role_gaps.items())
                if count.gap_count > 0
            ],
            skill_gaps=[
                NamedGap(name=names.skills[skill_id], gap_count=count.gap_count)
                for skill_id, count in sorted(result.skill_gaps.items())
                if count.gap_count > 0
            ],
            case_id=cases.get(shift.id),
        )
        for shift, result in short
    ]


def _pending_approvals(db: Session, scope: WardScope) -> list[WardCount]:
    """Requests of the approvals page that still wait for each visible ward's decision.

    A transfer needs both wards: it counts for each ward that has not approved yet.
    """
    counts: dict[int, int] = {}
    for request in approval_service.list_pending(db):
        for ward in request.wards:
            if ward.status == "PENDING" and scope.sees(ward.ward_id):
                counts[ward.ward_id] = counts.get(ward.ward_id, 0) + 1
    return [WardCount(ward_id=ward_id, count=count) for ward_id, count in sorted(counts.items())]


def _open_offers(db: Session, scope: WardScope, now: datetime) -> int:
    """Offers sent and still open for a reply, on running cases of visible wards."""
    return db.execute(
        select(func.count())
        .select_from(CandidateOutreach)
        .join(StaffingCase, StaffingCase.id == CandidateOutreach.case_id)
        .join(Shift, Shift.id == StaffingCase.shift_id)
        .where(
            Shift.ward_id.in_(scope.ward_ids),
            CandidateOutreach.status == OutreachStatus.SENT,
            CandidateOutreach.expires_at > now,
            StaffingCase.status.not_in(list(AUTOMATION_STOPPED_STATUSES)),
        )
    ).scalar_one()


def _recent_no_shows(db: Session, scope: WardScope) -> list[NoShowEvent]:
    """The NO_SHOW job's events: STAFF_UNAVAILABLE with payload.reason NO_SHOW (6.24)."""
    rows = db.execute(
        select(
            StaffingEvent.id,
            StaffingEvent.shift_id,
            StaffingEvent.staff_id,
            StaffingEvent.occurred_at,
        )
        .join(Shift, Shift.id == StaffingEvent.shift_id)
        .where(
            Shift.ward_id.in_(scope.ward_ids),
            StaffingEvent.event_type == EventType.STAFF_UNAVAILABLE,
            StaffingEvent.payload["reason"].as_string() == NO_SHOW_REASON,
        )
        .order_by(StaffingEvent.occurred_at.desc(), StaffingEvent.id.desc())
        .limit(DASHBOARD_MAX_NO_SHOWS)
    )
    return [
        NoShowEvent(event_id=event_id, shift_id=shift_id, staff_id=staff_id, created_at=at)
        for event_id, shift_id, staff_id, at in rows
    ]


def _llm_usage(db: Session, now: datetime) -> LlmUsage:
    """Today's DEMO count and this month's cost of every work type (6.27, 6.28).

    The day is the counter's own key, by the database's real time. The month follows
    LLM_CALL_LOG.started_at, which the gateway writes from the Backend Clock.
    """
    day = llm_gateway.quota_day(db)
    used = db.scalar(select(LlmDailyUsage.used).where(LlmDailyUsage.usage_date == day)) or 0
    local = now.astimezone(ZoneInfo(settings.llm_quota_timezone))
    month_start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    next_month = (month_start + timedelta(days=32)).replace(day=1)
    spend = llm_gateway.spend(db, start_at=month_start, end_at=next_month)
    return LlmUsage(
        date=day,
        used=used,
        cap=settings.llm_daily_call_cap,
        month_cost_usd=spend.known_usd,
        month_calls_without_cost=spend.unknown_calls,
        budget_usd=settings.llm_monthly_budget_usd,
    )
