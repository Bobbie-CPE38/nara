"""Demo control (docs/workflow.md 6.17, 6.33.5). On AWS the whole prefix is behind its own
Basic Auth, and in session mode every POST also needs an allowed Origin (6.33.3)."""

import csv
import io
import logging
from datetime import date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Response, status
from sqlalchemy import select

from app.api.dependencies import DbSession, Reader, access_viewer, forbidden
from app.api.offer_responses import ResponseResult
from app.core import clock
from app.core.constants import HEAD_NURSE_ROLE
from app.db.models import (
    Attendance,
    CandidateItem,
    CandidateOutreach,
    DemoDataset,
    Role,
    RosterAssignment,
    Shift,
    Staff,
    Ward,
)
from app.domain.enums import ActorName, CheckInSource, OutreachStatus, StaffStatus
from app.domain.errors import ShiftNotFoundError, StaffNotFoundError
from app.schemas.attendance import CheckInResponse, SimulatedCheckIn
from app.schemas.clock import ClockSet, ClockView, DemoReset
from app.schemas.demo import DemoOffer, DemoOfferAnswer, DemoRosterPerson, DemoShift, DemoWard
from app.schemas.event import DemoEventCreate, EventResult
from app.schemas.job import ClockAdvance, ClockAdvanceResult
from app.schemas.test_run import TestRunAbort, TestRunClosed, TestRunStart, TestRunStarted
from app.schemas.types import MAX_BIGINT
from app.seed import hospital_demo
from app.seed.reset import reset_demo
from app.services import (
    actor_service,
    attendance_service,
    demo_account_service,
    demo_example_service,
    event_service,
    job_service,
    outreach_service,
    test_run_service,
    unavailability_service,
)
from app.services.requirement_service import RequirementNotFoundError

# payload.source of an event the Demo control simulates (6.33.4)
SIMULATED_SOURCE = CheckInSource.SIMULATED.value

router = APIRouter(prefix="/demo", tags=["demo"])
logger = logging.getLogger(__name__)


def _run_in_progress(error: test_run_service.TestRunOpenError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(error))


@router.post("/reset")
def reset(db: DbSession, body: DemoReset | None = None) -> dict[str, str]:
    """Drop the database, migrate, load the Golden Case and freeze the clock at D 21:00.

    `hospital` adds or leaves out the hospital demo (6.36.3); no body keeps what the
    database had. Logins and LINE bindings stay (6.36.2).
    409 while a test run is open: it would wipe the run's case (6.35.2).
    """
    try:
        with test_run_service.no_open_run():
            demo_time = reset_demo(hospital=None if body is None else body.hospital)
            # Round 6 PR EV7: the hospital demo's example cases (6.37.1) and the test
            # accounts (6.37.9), under the same lock so a test run cannot start in between
            db.expire_all()
            if db.scalar(
                select(DemoDataset.id).where(DemoDataset.profile == hospital_demo.PROFILE)
            ):
                demo_example_service.play(db)
            # The reset has committed: a failure here must not answer 500 for it. The
            # accounts are made again by the next reset, which skips those that exist
            try:
                demo_account_service.ensure(db)
            except Exception:
                db.rollback()
                logger.exception("Demo reset: the test accounts were not made")
    except test_run_service.TestRunOpenError as error:
        raise _run_in_progress(error) from error
    return {"status": "ok", "clock": demo_time.isoformat()}


@router.post("/clock/advance")
def advance_clock(body: ClockAdvance, db: DbSession) -> ClockAdvanceResult:
    """Move the frozen demo clock, a running one (6.36.1) or a test run's clock forward,
    then expire offers, recover cases and close due windows.

    Runs the same function as the job service: a frozen clock that moves does
    not wake the job up. 409 when the clock follows real time (no reset yet since
    the backend started). In scenario mode the move adds to the run's offset and goes
    one job round at a time, two hours in all per run (test_run_service.advance_clock,
    6.35.1): 422 past that.
    """
    if clock.mode() == clock.ClockMode.REAL:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The demo clock is not frozen. Call POST /demo/reset first"
        )
    try:
        now, works = test_run_service.advance_clock(db, body.seconds)
    except test_run_service.AdvanceLimitError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    except RuntimeError as error:
        # Unfrozen between the check above and the move; PartialAdvanceError says how far
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    return ClockAdvanceResult.of(now, job_service.merge(works))


@router.post("/clock/freeze")
def freeze_clock() -> ClockView:
    """Freeze the clock at the time it shows now. Already frozen: nothing changes.
    409 while a test run is open (6.35.2)."""
    try:
        with test_run_service.no_open_run():
            clock.freeze_now()
    except test_run_service.TestRunOpenError as error:
        raise _run_in_progress(error) from error
    return ClockView.current()


@router.post("/clock/unfreeze")
def unfreeze_clock() -> ClockView:
    """Let the clock follow real time again (POST /demo/reset freezes it once more).
    409 while a test run is open (6.35.2)."""
    try:
        with test_run_service.no_open_run():
            clock.reset()
    except test_run_service.TestRunOpenError as error:
        raise _run_in_progress(error) from error
    return ClockView.current()


@router.post("/clock/resume")
def resume_clock() -> ClockView:
    """Let the clock run on at real speed from the time it shows now, frozen or not
    (running mode, 6.36.1). 409 while a test run is open (6.35.2)."""
    try:
        with test_run_service.no_open_run():
            clock.run_from(clock.now())
    except test_run_service.TestRunOpenError as error:
        raise _run_in_progress(error) from error
    return ClockView.current()


@router.post("/clock/set")
def set_clock(body: ClockSet) -> ClockView:
    """Put the clock at any time within a year of real time, frozen there or running on
    from it (6.36.1). Back or forward: the job runs what fell due on its next round.
    409 while a test run is open (6.35.2); 422 for a time out of range."""
    try:
        with test_run_service.no_open_run():
            if body.running:
                clock.run_from(body.at)
            else:
                clock.set_time(body.at)
    except test_run_service.TestRunOpenError as error:
        raise _run_in_progress(error) from error
    return ClockView.current()


def _manager_only(db: DbSession, reader: Reader) -> None:
    """In session mode the Demo control's reads of people need a head nurse or a supervisor,
    like its events (6.33.4); demo mode asks nobody."""
    if reader is not None and access_viewer(db, reader).role == "staff":
        raise forbidden()


@router.get("/wards")
def list_wards(db: DbSession, reader: Reader) -> list[DemoWard]:
    """Every ward, for the Demo control's choice of shift (round 6 PR EV6, 6.36.5)."""
    _manager_only(db, reader)
    head_nurses: dict[int, int] = {}
    for ward_id, staff_id in db.execute(
        select(Staff.home_ward_id, Staff.id)
        .join(Role, Role.id == Staff.role_id)
        .where(Role.name == HEAD_NURSE_ROLE, Staff.status == StaffStatus.ACTIVE)
        .order_by(Staff.id)
    ):
        head_nurses.setdefault(ward_id, staff_id)
    return [
        DemoWard(
            id=ward.id,
            name=ward.name,
            is_active=ward.is_active,
            is_float_pool=ward.is_float_pool,
            head_nurse_id=head_nurses.get(ward.id),
        )
        for ward in db.scalars(select(Ward).order_by(Ward.id))
    ]


@router.get("/offers")
def list_open_offers(db: DbSession, reader: Reader) -> list[DemoOffer]:
    """Every offer a candidate can still answer, for the Demo control to answer in their
    place (round 6 PR EV7, 6.37.8). Oldest first."""
    _manager_only(db, reader)
    now = clock.now()
    staff_ids = db.scalars(
        select(CandidateItem.staff_id)
        .join(CandidateOutreach, CandidateOutreach.candidate_item_id == CandidateItem.id)
        .where(
            CandidateOutreach.status == OutreachStatus.SENT,
            CandidateOutreach.expires_at > now,
        )
        .distinct()
    ).all()
    names = {staff.id: staff for staff in db.scalars(select(Staff).where(Staff.id.in_(staff_ids)))}
    offers = [
        DemoOffer(
            **offer.model_dump(),
            first_name=names[offer.staff_id].first_name,
            last_name=names[offer.staff_id].last_name,
        )
        for offer in outreach_service.list_offers_of(db, set(staff_ids))
        if offer.can_accept or offer.can_reject
    ]
    return sorted(offers, key=lambda offer: (offer.sent_at is None, offer.sent_at, offer.id))


@router.post("/offers/{outreach_id}/response")
def answer_open_offer(
    outreach_id: Annotated[int, Path(ge=1, le=MAX_BIGINT)],
    body: DemoOfferAnswer,
    db: DbSession,
    reader: Reader,
) -> ResponseResult:
    """Answer an offer as its candidate, through the same service as the candidate's own
    answer, in their name with payload.source SIMULATED (6.37.8). 404 unknown offer, 409
    when it can no longer be answered."""
    _manager_only(db, reader)
    staff_id = db.scalar(
        select(CandidateItem.staff_id)
        .join(CandidateOutreach, CandidateOutreach.candidate_item_id == CandidateItem.id)
        .where(CandidateOutreach.id == outreach_id)
    )
    if staff_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No offer {outreach_id}")
    try:
        outreach, case = outreach_service.record_response(
            db,
            staff_id=staff_id,
            actor_id=actor_service.user_id(db, staff_id),
            outreach_id=outreach_id,
            response=body.response,
            audit_source=SIMULATED_SOURCE,
        )
    except outreach_service.OutreachLockRetryError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error), headers={"Retry-After": "1"}
        ) from error
    except outreach_service.OpenOfferConflictError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(error)) from error
    return ResponseResult(
        outreach_id=outreach.id,
        outreach_status=outreach.status,
        case_id=case.id,
        case_status=case.status,
    )


@router.get("/shifts")
def list_shifts(
    db: DbSession,
    reader: Reader,
    ward_id: Annotated[int, Query(ge=1, le=MAX_BIGINT)],
    day: Annotated[date, Query(alias="date", ge=date(2000, 1, 1), le=date(2999, 12, 31))],
) -> list[DemoShift]:
    """Shifts of any ward starting on `date` (Asia/Bangkok), each with every roster row and
    whether the person has checked in: whom the Demo control can check in or report on
    leave (6.36.5). Active shifts only, like the gap check; an unknown ward has none."""
    _manager_only(db, reader)
    start = datetime.combine(day, time(), tzinfo=clock.APP_TIMEZONE)
    shifts = db.scalars(
        select(Shift)
        .where(
            Shift.ward_id == ward_id,
            Shift.is_active.is_(True),
            Shift.start_at >= start,
            Shift.start_at < start + timedelta(days=1),
        )
        .order_by(Shift.start_at, Shift.id)
    ).all()
    if not shifts:
        return []
    rows = db.execute(
        select(RosterAssignment, Staff)
        .join(Staff, Staff.id == RosterAssignment.staff_id)
        .where(RosterAssignment.shift_id.in_([shift.id for shift in shifts]))
        .order_by(RosterAssignment.staff_id, RosterAssignment.id)
    ).all()
    arrived = {
        (shift_id, staff_id)
        for shift_id, staff_id in db.execute(
            select(Attendance.shift_id, Attendance.staff_id).where(
                Attendance.shift_id.in_([shift.id for shift in shifts])
            )
        )
    }
    people: dict[int, list[DemoRosterPerson]] = {shift.id: [] for shift in shifts}
    for roster, staff in rows:
        people[roster.shift_id].append(
            DemoRosterPerson(
                staff_id=staff.id,
                first_name=staff.first_name,
                last_name=staff.last_name,
                status=roster.status,
                checked_in=(roster.shift_id, staff.id) in arrived,
            )
        )
    return [
        DemoShift(
            id=shift.id,
            ward_id=shift.ward_id,
            shift_type=shift.shift_type,
            start_at=shift.start_at,
            end_at=shift.end_at,
            people=people[shift.id],
        )
        for shift in shifts
    ]


@router.post("/attendance/check-in")
def simulate_check_in(body: SimulatedCheckIn, db: DbSession) -> CheckInResponse:
    """Simulate the arrival of a character: no X-Demo-User, audit source SIMULATED by SYSTEM.

    Same function and answers as POST /me/attendance/check-in, plus 404 for an
    unknown staff ID. Must stay unreachable from the public channel (section 6.24).
    """
    try:
        if db.get(Staff, body.staff_id) is None:
            raise StaffNotFoundError(f"No staff {body.staff_id}")
        result = attendance_service.check_in(
            db,
            staff_id=body.staff_id,
            shift_id=body.shift_id,
            source=CheckInSource.SIMULATED,
            actor_id=actor_service.component_id(db, ActorName.SYSTEM),
        )
    except (
        StaffNotFoundError,
        ShiftNotFoundError,
        unavailability_service.NoAssignedRosterError,
    ) as error:
        db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except attendance_service.CheckInOutsideWindowError as error:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    except attendance_service.CheckInLockRetryError as error:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    return CheckInResponse(**vars(result))


@router.post("/events", status_code=status.HTTP_201_CREATED)
def simulate_event(body: DemoEventCreate, db: DbSession, reader: Reader) -> EventResult:
    """The Demo control's events, now that POST /events refuses web accounts (6.33.4).

    The same validation and service as POST /events, as the demo character in
    `reporter_staff_id`, but recorded by the SYSTEM actor with payload.source SIMULATED, and
    every audit row it makes while the event is applied is by SYSTEM as well: never a report
    of a signed-in user. In demo mode no session is needed; on AWS this path is behind
    the Demo Basic Auth (6.33.5). Answers as POST /events, plus 404 for an unknown or
    inactive character. None of the errors writes anything.

    Session mode needs a session of a head nurse or a supervisor as well, whatever stands in
    front of the machine: Basic Auth alone is not the only guard of a call that cancels roster
    rows or changes a requirement (401 without a session, 403 for a nurse). Demo mode asks nobody.
    """
    if reader is not None and access_viewer(db, reader).role == "staff":
        raise forbidden()
    reporter = db.get(Staff, body.reporter_staff_id)
    if reporter is None or reporter.status != StaffStatus.ACTIVE:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No active staff {body.reporter_staff_id}")
    try:
        outcome = event_service.receive_event(
            db,
            staff_id=reporter.id,
            actor_id=actor_service.component_id(db, ActorName.SYSTEM),
            role_id=reporter.role_id,
            event_type=body.event_type,
            shift_id=body.shift_id,
            end_at=body.end_at,
            target_staff_id=body.staff_id,
            reason=body.reason,
            patient_count=body.patient_count,
            roles=None
            if body.roles is None
            else {item.role_id: item.required_count for item in body.roles},
            skills=None
            if body.skills is None
            else {item.skill_id: item.required_count for item in body.skills},
            source=SIMULATED_SOURCE,
        )
    except event_service.ShiftNotFoundError as error:
        db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except RequirementNotFoundError as error:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except event_service.NotHeadNurseError as error:
        db.rollback()
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    except unavailability_service.NoAssignedRosterError as error:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except (event_service.InvalidEventDetailsError, event_service.InvalidLeaveEndError) as error:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    return EventResult(
        event_id=outcome.event_id,
        event_status=outcome.event_status,
        case_id=outcome.case_id,
        case_status=outcome.case_status,
    )


# --------------------------------------------------------------------------- #
# Test runs (round 6 PR EV5a, docs/workflow.md 6.35.2)
# --------------------------------------------------------------------------- #
def _manager(db: DbSession, reader: Reader) -> int | None:
    """As POST /demo/events: a head nurse or supervisor in session mode (401/403), nobody
    in demo mode. Returns the signed-in staff ID, which the run's rows are written by."""
    if reader is None:
        return None
    if access_viewer(db, reader).role == "staff":
        raise forbidden()
    return reader.staff.id


@router.post("/test-runs", status_code=status.HTTP_201_CREATED)
def start_test_run(body: TestRunStart, db: DbSession, reader: Reader) -> TestRunStarted:
    """Reset, load the scenario, start the scenario clock at D 21:00 and open the case.
    409 while another run is open."""
    staff_id = _manager(db, reader)
    db.close()  # the reset drops the schema: hold no connection of this request
    try:
        started = test_run_service.start(
            tester_code=body.tester_code,
            scenario=body.scenario,
            auto_nurses=body.auto_nurses,
            staff_id=staff_id,
        )
    except test_run_service.TestRunOpenError as error:
        raise _run_in_progress(error) from error
    return TestRunStarted(**vars(started))


def _close_run(
    db: DbSession, reader: Reader, test_run_id: int, reason: str | None, *, aborted: bool
) -> TestRunClosed:
    staff_id = _manager(db, reader)
    try:
        if aborted:
            result = test_run_service.abort(db, test_run_id, reason=reason, staff_id=staff_id)
        else:
            result = test_run_service.finish(db, test_run_id, staff_id=staff_id)
    except test_run_service.TestRunNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except test_run_service.TestRunClosedError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    return TestRunClosed(test_run_id=test_run_id, result=result)


@router.post("/test-runs/{test_run_id}/finish")
def finish_test_run(test_run_id: int, db: DbSession, reader: Reader) -> TestRunClosed:
    """Freeze the clock and store the KPI. After an API restart the run closes as CLOCK_LOST."""
    return _close_run(db, reader, test_run_id, None, aborted=False)


@router.post("/test-runs/{test_run_id}/abort")
def abort_test_run(
    test_run_id: int, db: DbSession, reader: Reader, body: TestRunAbort | None = None
) -> TestRunClosed:
    """Close the run without KPI (invalid, reason ABORTED or the one given)."""
    return _close_run(db, reader, test_run_id, None if body is None else body.reason, aborted=True)


@router.get("/test-runs")
def list_test_runs(db: DbSession, reader: Reader) -> list[test_run_service.RunView]:
    """Every run in start order, open ones with the time so far."""
    _manager(db, reader)
    return test_run_service.list_runs(db)


@router.get("/test-runs.csv")
def test_runs_csv(db: DbSession, reader: Reader) -> Response:
    """One row per closed run (6.35.2)."""
    _manager(db, reader)
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=test_run_service.CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(test_run_service.csv_rows(db))
    return Response(
        out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="test-runs.csv"'},
    )
