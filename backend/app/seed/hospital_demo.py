"""The hospital demo: five more wards and a Float Pool for a week (round 6 PR EV6, 6.36.3).

Added on top of the Golden Case, which stays as it is for the tests and the test runs.
A demo reset with `hospital=True` loads it, and the next resets keep loading it until a
reset says otherwise (a DEMO_DATASET row, like the large profile). It writes no account,
contact, event or case: the demo starts calm, and the Demo control makes the trouble.

Once loaded, its people are permanent like everyone else (6.33.7): a reset with
`hospital=False` keeps the wards and the people but pauses them, inactive and without
shifts (the PAUSED_PROFILE row). Dropping the wards would fail the reset, because a kept
person must find their ward again.

Each ward has a head nurse and 15 RNs in three teams, one per shift type (day 07-15,
evening 15-23, night 23-07). Every day one nurse of each team is off in turn, so every
shift has 4 people: exactly the required staff, 1 above the minimum. The week runs from
D-3 to D+3, so the week's hours and the consecutive shifts differ from person to person,
which the ranking reads. Shifts that ended before the reset are COMPLETED; the evening
shift of D is running and its people are checked in by seed.check_ins.

The people of these wards check in on time by themselves (check_in_arrivals(), from the
due-work job): without it, every shift start would turn 20 people into NO_SHOW cases.
Someone with a leave or a reported absence for the shift does not arrive. A test run
pauses these wards (6.35.3), so they then neither arrive nor join a pool.
"""

from datetime import datetime, timedelta

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    Actor,
    Attendance,
    DemoDataset,
    RosterAssignment,
    Shift,
    Staff,
    StaffingEvent,
    StaffingRequirement,
    StaffingRequirementRole,
    StaffingRequirementSkill,
    StaffSkill,
    StaffUnavailability,
    Ward,
)
from app.domain.enums import (
    STAFF_EVENT_TYPES,
    ActorName,
    ActorType,
    AssignmentType,
    CheckInSource,
    RosterStatus,
    ShiftType,
    StaffStatus,
)
from app.seed import staff_subject, sync_sequences

PROFILE = "hospital-5-wards-7-days-v1"
PAUSED_PROFILE = f"{PROFILE}-paused"
PROFILES = (PROFILE, PAUSED_PROFILE)
# Above the Golden Case and the large profile (10_001-10_020, 100_001-, 2_000_001-), and
# above test_run_service's WARD_BASE, so a test run pauses these wards too
WARD_BASE, STAFF_BASE, SHIFT_BASE = 20_000, 200_000, 3_000_000
WARD_NAMES = ("Surgery", "Pediatrics", "Emergency", "Orthopedics", "Cardiology")
FLOAT_POOL_WARD = WARD_BASE + len(WARD_NAMES) + 1
TEAM_SIZE, FLOAT_POOL_SIZE = 5, 4
DAYS_BEFORE, DAYS_AFTER = 3, 3
PATIENTS_PER_SHIFT, REQUIRED_STAFF, MINIMUM_STAFF, REQUIRED_BLS = 8, 4, 3, 2
RN_ROLE, HEAD_NURSE_ROLE = 1, 2
ICU_SKILL, BLS_SKILL = 1, 2
# (shift type, start hour); the night shift ends at 07 the next day
SHIFT_TYPES = ((ShiftType.DAY, 7), (ShiftType.EVENING, 15), (ShiftType.NIGHT, 23))
SHIFT_HOURS = 8

FIRST_NAMES = (
    "Achara",
    "Boonmee",
    "Chalerm",
    "Duangjai",
    "Ekkachai",
    "Fongchan",
    "Ganya",
    "Hathai",
    "Itsara",
    "Jintana",
    "Kamon",
    "Lamai",
    "Manee",
    "Nattapong",
    "Orathai",
    "Pakorn",
    "Rattana",
    "Saowanee",
    "Tawan",
    "Usa",
    "Wilai",
    "Yupin",
    "Anong",
    "Busaba",
)
LAST_NAMES = (
    "Srisuk",
    "Thongdee",
    "Kaewmanee",
    "Boonyarat",
    "Chaiyaporn",
    "Rungruang",
    "Saetang",
    "Wongsa",
    "Phromma",
    "Inthara",
    "Sukjai",
)


def ward_ids() -> list[int]:
    """The wards of the profile with shifts of their own (not the Float Pool)."""
    return [WARD_BASE + index + 1 for index in range(len(WARD_NAMES))]


def _staff_id(ward_index: int, ordinal: int) -> int:
    """Ordinal 0 is the head nurse, 1-15 the RNs (team = (ordinal - 1) // TEAM_SIZE)."""
    return STAFF_BASE + ward_index * 100 + ordinal + 1


def _float_staff_id(ordinal: int) -> int:
    return STAFF_BASE + 90 + ordinal + 1


def _name(staff_id: int) -> tuple[str, str]:
    return (
        FIRST_NAMES[staff_id % len(FIRST_NAMES)],
        LAST_NAMES[(staff_id // 7) % len(LAST_NAMES)],
    )


def seed(db: Session, *, active: bool = True) -> None:
    """Load the profile on the frozen demo clock (D 21:00), after the Golden Case and
    before seed.check_ins. `active=False` loads the wards inactive and the people without
    shifts. Flushes; the caller commits."""
    now = clock.now()
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    db.add(DemoDataset(profile=PROFILE if active else PAUSED_PROFILE, reference_at=now))
    for index, name in enumerate(WARD_NAMES):
        db.add(
            Ward(
                id=WARD_BASE + index + 1,
                name=name,
                is_active=active,
                created_at=now,
                updated_at=now,
            )
        )
    db.add(
        Ward(
            id=FLOAT_POOL_WARD,
            name="Hospital Float Pool",
            is_active=active,
            is_float_pool=True,
            created_at=now,
            updated_at=now,
        )
    )
    db.flush()

    people: list[tuple[int, int, int, tuple[int, ...]]] = []  # id, role, ward, skills
    for index in range(len(WARD_NAMES)):
        ward_id = WARD_BASE + index + 1
        people.append((_staff_id(index, 0), HEAD_NURSE_ROLE, ward_id, ()))
        for ordinal in range(1, 3 * TEAM_SIZE + 1):
            # Every third RN also has the ICU skill
            rn_skills: tuple[int, ...] = (BLS_SKILL,) + ((ICU_SKILL,) if ordinal % 3 == 0 else ())
            people.append((_staff_id(index, ordinal), RN_ROLE, ward_id, rn_skills))
    for ordinal in range(FLOAT_POOL_SIZE):
        people.append((_float_staff_id(ordinal), RN_ROLE, FLOAT_POOL_WARD, (BLS_SKILL, ICU_SKILL)))
    for staff_id, role_id, ward_id, _ in people:
        first_name, last_name = _name(staff_id)
        db.add(
            Staff(
                id=staff_id,
                first_name=first_name,
                last_name=last_name,
                email=f"{staff_id}@demo.local",
                password_hash="!",
                role_id=role_id,
                home_ward_id=ward_id,
                status=StaffStatus.ACTIVE,
                auth_subject=staff_subject(db, staff_id),
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()
    for staff_id, _, _, skills in people:
        db.add(Actor(name=str(staff_id), actor_type=ActorType.USER, staff_id=staff_id))
        db.add_all(StaffSkill(staff_id=staff_id, skill_id=skill_id) for skill_id in skills)

    shift_id = SHIFT_BASE
    for index in range(len(WARD_NAMES) if active else 0):
        ward_id = WARD_BASE + index + 1
        for offset in range(-DAYS_BEFORE, DAYS_AFTER + 1):
            day = day0 + timedelta(days=offset)
            for team, (shift_type, start_hour) in enumerate(SHIFT_TYPES):
                shift_id += 1
                start_at = day + timedelta(hours=start_hour)
                end_at = start_at + timedelta(hours=SHIFT_HOURS)
                _add_shift(db, shift_id, ward_id, shift_type, start_at, end_at, now)
                # One nurse of the team is off each day, in turn
                off = (offset + DAYS_BEFORE + index) % TEAM_SIZE
                status = RosterStatus.COMPLETED if end_at <= now else RosterStatus.ASSIGNED
                db.add_all(
                    RosterAssignment(
                        staff_id=_staff_id(index, team * TEAM_SIZE + member + 1),
                        shift_id=shift_id,
                        status=status,
                        assignment_type=AssignmentType.REGULAR,
                        candidate_source=None,
                        created_at=now,
                        updated_at=now,
                    )
                    for member in range(TEAM_SIZE)
                    if member != off
                )
    sync_sequences(
        db,
        [
            Ward.__tablename__,
            Staff.__tablename__,
            Shift.__tablename__,
            StaffingRequirement.__tablename__,
        ],
    )


def _add_shift(
    db: Session,
    shift_id: int,
    ward_id: int,
    shift_type: ShiftType,
    start_at: datetime,
    end_at: datetime,
    now: datetime,
) -> None:
    db.add(
        Shift(
            id=shift_id,
            ward_id=ward_id,
            patient_count=PATIENTS_PER_SHIFT,
            start_at=start_at,
            end_at=end_at,
            shift_type=shift_type,
            is_active=True,
            merge_window_seconds=0,
        )
    )
    db.flush()
    db.add(
        StaffingRequirement(
            id=shift_id,
            shift_id=shift_id,
            required_staff=REQUIRED_STAFF,
            minimum_staff=MINIMUM_STAFF,
            created_at=now,
        )
    )
    db.flush()
    db.add(
        StaffingRequirementRole(
            staffing_requirement_id=shift_id, role_id=RN_ROLE, required_count=REQUIRED_STAFF
        )
    )
    db.add(
        StaffingRequirementSkill(
            staffing_requirement_id=shift_id, skill_id=BLS_SKILL, required_count=REQUIRED_BLS
        )
    )


def check_in_arrivals(db: Session) -> list[int]:
    """Check in, on time, the people of the profile whose shift has begun. Commits.

    Only ASSIGNED rows of active profile wards, from the required arrival until the
    effective end, without a check-in, a leave that overlaps the shift, or a reported
    absence still waiting for its window. Returns the new ATTENDANCE IDs.
    """
    # Imported here: the seed loaders stay free of service imports until the job calls this
    from app.services import actor_service, attendance_service, merge_window_service

    now = clock.now()
    reported = exists().where(
        StaffingEvent.shift_id == RosterAssignment.shift_id,
        StaffingEvent.staff_id == RosterAssignment.staff_id,
        StaffingEvent.event_type.in_(list(STAFF_EVENT_TYPES)),
    )
    checked_in = exists().where(
        Attendance.shift_id == RosterAssignment.shift_id,
        Attendance.staff_id == RosterAssignment.staff_id,
    )
    on_leave = exists().where(
        StaffUnavailability.staff_id == RosterAssignment.staff_id,
        StaffUnavailability.start_at < Shift.end_at,
        (StaffUnavailability.end_at.is_(None)) | (StaffUnavailability.end_at > Shift.start_at),
    )
    due = db.execute(
        select(RosterAssignment.shift_id, RosterAssignment.id)
        .join(Shift, Shift.id == RosterAssignment.shift_id)
        .join(Ward, Ward.id == Shift.ward_id)
        .where(
            Ward.id > WARD_BASE,
            Ward.id <= FLOAT_POOL_WARD,
            Ward.is_active.is_(True),
            Shift.start_at <= now,
            Shift.end_at > now,
            RosterAssignment.status == RosterStatus.ASSIGNED,
            ~checked_in,
            ~reported,
            ~on_leave,
        )
        .order_by(RosterAssignment.shift_id, RosterAssignment.id)
    ).all()
    if not due:
        return []
    actor_id = actor_service.component_id(db, ActorName.SYSTEM)
    by_shift: dict[int, list[int]] = {}
    for shift_id, row_id in due:
        by_shift.setdefault(shift_id, []).append(row_id)
    attendance_ids: list[int] = []
    for shift_id, row_ids in by_shift.items():
        # Shift, then its roster rows: the lock order of a check-in (6.11)
        shift = merge_window_service.lock_shift(db, shift_id)
        rows = db.scalars(
            select(RosterAssignment)
            .where(RosterAssignment.id.in_(row_ids))
            .order_by(RosterAssignment.id)
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        ).all()
        for roster in rows:
            arrival = attendance_service.required_arrival_at(roster, shift)
            already = db.scalar(
                select(Attendance.id).where(
                    Attendance.shift_id == shift.id, Attendance.staff_id == roster.staff_id
                )
            )
            if roster.status != RosterStatus.ASSIGNED or already is not None or arrival > now:
                continue
            result = attendance_service.record(
                db,
                roster=roster,
                shift=shift,
                check_in_at=arrival,
                source=CheckInSource.SIMULATED,
                actor_id=actor_id,
            )
            attendance_ids.append(result.attendance_id)
        db.commit()
    return attendance_ids
