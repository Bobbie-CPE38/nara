"""
GET /dashboard: one read of what needs attention now (docs/workflow.md 6.31, 9.8).

Round 6 PR F1. Reads only: no flush of new rows, no lock, no commit. Every number is
limited to the wards the demo user sees (`gap_check_service.ward_scope`, R6-Q16 ก).
Since round 6 PR EV8 the Dashboard is for head nurses and supervisors only in session mode
(the route refuses a nurse), so every number here is by ward.
The gap is measured only for shifts in progress or starting within
DASHBOARD_SHORTAGE_WINDOW_HOURS of the Backend Clock, so the cost of a refresh does
not grow with every shift in the system (about 4.5 ms per shift at demo scale). Every shift
of that window is measured, so the cards and the chart count all of them, while the list
keeps the first DASHBOARD_MAX_SHORTAGES.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import settings
from app.core.constants import (
    DASHBOARD_MAX_NO_SHOWS,
    DASHBOARD_MAX_SHORTAGES,
    DASHBOARD_SHORTAGE_WINDOW_HOURS,
    HEAD_NURSE_ROLE,
)
from app.db.models import (
    CandidateItem,
    CandidateOutreach,
    LlmDailyUsage,
    Role,
    Shift,
    Staff,
    StaffingCase,
    StaffingEvent,
    Ward,
)
from app.domain.enums import (
    AUTOMATION_STOPPED_STATUSES,
    CaseStatus,
    EventType,
    OutreachStatus,
    StaffStatus,
)
from app.domain.staffing.gap_calculator import GapResult
from app.domain.staffing.ward_authority import can_decide
from app.schemas.dashboard import (
    Approver,
    CaseStatusCount,
    Dashboard,
    DashboardModes,
    DashboardSummary,
    LlmUsage,
    NamedGap,
    NoShowEvent,
    OpenOffers,
    PendingApprovalCount,
    Shortage,
    WardOption,
    WardShortage,
)
from app.services import approval_service, gap_check_service, llm_gateway
from app.services.gap_check_service import WardScope
from app.services.merge_window_service import NO_SHOW_REASON

# Every seed loader gives its people an address here (seed/hospital_demo.py, the Golden
# Case, the large profile): wards staffed by them show demo data, not a hospital's
DEMO_EMAIL_DOMAIN = "@demo.local"


class WardNotVisibleError(ValueError):
    """?ward_id= names a ward the user does not see (or that does not exist)."""


@dataclass(frozen=True)
class _Short:
    shift: Shift
    result: GapResult


def build(db: Session, staff: Staff, *, ward_id: int | None = None) -> Dashboard:
    """`ward_id` narrows every number to one of the user's wards (round 6 PR EV6, 6.36.4).

    Without `ward_id` the numbers cover the active wards a user sees, as before. A Supervisor
    may also pick a paused ward, for example the hospital demo during a test run (review of
    #145): it is listed after the active ones with is_active false."""
    visible = gap_check_service.ward_scope(db, staff)
    wards = db.execute(select(Ward.id, Ward.name, Ward.is_active).order_by(Ward.id)).all()
    listed = [row for row in wards if row.id in visible.ward_ids]
    if gap_check_service.is_supervisor(db, staff):
        listed += [row for row in wards if not row.is_active]
    if ward_id is not None and ward_id not in {row.id for row in listed}:
        raise WardNotVisibleError(f"Ward {ward_id} is not one of your wards")
    scope = visible if ward_id is None else WardScope(ward_ids=(ward_id,))
    now = clock.now()
    with db.no_autoflush:
        cases_by_status = _cases_by_status(db, scope)
        short = _short_shifts(db, scope, now)
        pending = _pending_approvals(db, scope, now, staff)
        return Dashboard(
            now=now,
            modes=DashboardModes(
                line_mode=settings.line_mode,
                llm_provider=settings.llm_provider,
                llm_enabled=settings.llm_enabled,
            ),
            wards=list(scope.ward_ids),
            ward_options=[
                WardOption(id=row.id, name=row.name, is_active=row.is_active) for row in listed
            ],
            window_hours=DASHBOARD_SHORTAGE_WINDOW_HOURS,
            demo_data=_demo_data(db, scope),
            summary=DashboardSummary(
                short_shifts=len(short),
                missing_positions=sum(row.result.headcount_gap for row in short),
                pending_approvals=len(pending.decidable),
                pending_approvals_later=len(pending.request_ids - pending.decidable),
                handoff_cases=next(
                    row.count for row in cases_by_status if row.status is CaseStatus.MANUAL_HANDOFF
                ),
            ),
            cases_by_status=cases_by_status,
            shortages=_shortage_rows(db, short[:DASHBOARD_MAX_SHORTAGES], now),
            shortage_by_ward=_by_ward(short),
            pending_approvals=pending.rows,
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


def _short_shifts(db: Session, scope: WardScope, now: datetime) -> list[_Short]:
    """Every short shift of the window: running ones first, then by start (EV8). A running
    shift started before every later one, so the order of the start is that order."""
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
        if assessment.result.has_gap:
            short.append(_Short(shift, assessment.result))
    return short


def _shortage_rows(db: Session, short: list[_Short], now: datetime) -> list[Shortage]:
    """The rows of the urgent list, with the running case of each shift."""
    names = gap_check_service.names_of(
        db,
        {role_id for row in short for role_id in row.result.role_gaps},
        {skill_id for row in short for skill_id in row.result.skill_gaps},
    )
    running = gap_check_service.running_case_ids(db, [row.shift.id for row in short])
    return [
        Shortage(
            shift_id=row.shift.id,
            ward_id=row.shift.ward_id,
            start_at=row.shift.start_at,
            end_at=row.shift.end_at,
            headcount_gap=row.result.headcount_gap,
            role_gaps=[
                NamedGap(name=names.roles[role_id], gap_count=count.gap_count)
                for role_id, count in sorted(row.result.role_gaps.items())
                if count.gap_count > 0
            ],
            skill_gaps=[
                NamedGap(name=names.skills[skill_id], gap_count=count.gap_count)
                for skill_id, count in sorted(row.result.skill_gaps.items())
                if count.gap_count > 0
            ],
            case_id=running.get(row.shift.id),
            in_progress=row.shift.start_at <= now,
        )
        for row in short
    ]


def _by_ward(short: list[_Short]) -> list[WardShortage]:
    """One bar per ward with a short shift: the most positions missing first, then by ID."""
    totals: dict[int, list[int]] = {}
    for row in short:
        positions, shifts = totals.setdefault(row.shift.ward_id, [0, 0])
        totals[row.shift.ward_id] = [positions + row.result.headcount_gap, shifts + 1]
    return sorted(
        (
            WardShortage(ward_id=ward_id, missing_positions=positions, short_shifts=shifts)
            for ward_id, (positions, shifts) in totals.items()
        ),
        key=lambda row: (-row.missing_positions, row.ward_id),
    )


@dataclass(frozen=True)
class _Pending:
    rows: list[PendingApprovalCount]
    # Every request with a side of a ward shown still to decide
    request_ids: set[int]
    # Those the user may decide now (ward_authority.can_decide): the card counts these
    decidable: set[int]


def _pending_approvals(db: Session, scope: WardScope, now: datetime, staff: Staff) -> _Pending:
    """Requests of the approvals page that still wait for each visible ward's decision, and
    who may decide them (EV8): the ward's head nurses, and the Supervisor once
    `supervisor_from` passed.

    A transfer needs both wards: it counts for each ward that has not approved yet. The
    requests the user may decide now are kept apart (review of #147): a Supervisor's
    approvals page lists a request only from `supervisor_from` on, so the card that links
    there counts the same requests.
    """
    role = db.scalar(select(Role.name).where(Role.id == staff.role_id))
    counts: dict[tuple[int, bool], int] = {}
    request_ids = set()
    decidable = set()
    for request in approval_service.list_pending(db):
        waited = now >= request.supervisor_from
        for ward in request.wards:
            if ward.status == "PENDING" and scope.sees(ward.ward_id):
                key = (ward.ward_id, waited)
                counts[key] = counts.get(key, 0) + 1
                request_ids.add(request.id)
                if can_decide(
                    role=role, home_ward_id=staff.home_ward_id, ward_id=ward.ward_id, waited=waited
                ):
                    decidable.add(request.id)
    heads = _head_nurses(db, {ward_id for ward_id, _ in counts})
    return _Pending(
        rows=[
            PendingApprovalCount(
                ward_id=ward_id,
                count=count,
                head_nurses=heads.get(ward_id, []),
                supervisor=supervisor,
            )
            for (ward_id, supervisor), count in sorted(counts.items())
        ],
        request_ids=request_ids,
        decidable=decidable,
    )


def _head_nurses(db: Session, ward_ids: set[int]) -> dict[int, list[Approver]]:
    """The active head nurses of each ward, by staff ID: the people who decide its side."""
    if not ward_ids:
        return {}
    heads: dict[int, list[Approver]] = {}
    for staff_id, first, last, ward_id in db.execute(
        select(Staff.id, Staff.first_name, Staff.last_name, Staff.home_ward_id)
        .join(Role, Role.id == Staff.role_id)
        .where(
            Staff.home_ward_id.in_(ward_ids),
            Role.name == HEAD_NURSE_ROLE,
            Staff.status == StaffStatus.ACTIVE,
        )
        .order_by(Staff.id)
    ):
        heads.setdefault(ward_id, []).append(Approver(staff_id=staff_id, name=f"{first} {last}"))
    return heads


def _demo_data(db: Session, scope: WardScope) -> bool:
    """The wards shown are staffed by the demo's simulated people."""
    return bool(
        db.scalar(
            select(
                exists().where(
                    Staff.home_ward_id.in_(scope.ward_ids),
                    Staff.email.endswith(DEMO_EMAIL_DOMAIN),
                )
            )
        )
    )


def _open_offers(db: Session, scope: WardScope, now: datetime) -> int:
    """Offers sent and still open for a reply, on running cases of visible wards."""
    return db.execute(
        select(func.count())
        .select_from(CandidateOutreach)
        .join(StaffingCase, StaffingCase.id == CandidateOutreach.case_id)
        .join(Shift, Shift.id == StaffingCase.shift_id)
        .join(CandidateItem, CandidateItem.id == CandidateOutreach.candidate_item_id)
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
