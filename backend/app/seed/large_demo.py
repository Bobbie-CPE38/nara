"""Additive, offline 500-person / 20-ward / 30-day fixture, never a live workflow.

Only this versioned namespace is owned by the loader. No account, contact, LINE
intent, live case or LLM row is made. Historical cases are explicitly synthetic.
The caller owns one transaction; a namespace collision refuses the whole import.
"""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    Actor,
    Attendance,
    AuditLog,
    DemoDataset,
    ManualAssignment,
    Role,
    RosterAssignment,
    Shift,
    Skill,
    Staff,
    StaffingCase,
    StaffingEvent,
    StaffingGap,
    StaffingGapInterval,
    StaffingGapRole,
    StaffingGapRoleInterval,
    StaffingGapSkill,
    StaffingGapSkillInterval,
    StaffingRequirement,
    StaffingRequirementRole,
    StaffingRequirementSkill,
    StaffSkill,
    StaffUnavailability,
    StructuredHandover,
    Ward,
)
from app.domain.enums import (
    ActorName,
    ActorType,
    AssignmentType,
    AuditAction,
    AvailabilityReason,
    CaseStatus,
    EntityType,
    EventStatus,
    EventType,
    RosterStatus,
    ShiftType,
    StaffStatus,
)
from app.seed import staff_subject, sync_sequences
from app.services import actor_service

PROFILE = "large-500-20-30-v1"
STAFF_BASE, WARD_BASE, SHIFT_BASE = 100_000, 10_000, 2_000_000
STAFF_COUNT, WARD_COUNT, DAYS = 500, 20, 30
FIRST_NAMES = ("กานต์", "พิมพ์ชนก", "ธนพร", "อรุณี", "วรรณา", "รัตนา", "นภัส", "ศิริ", "ปวีณา", "ณัฐ")
WARD_NAMES = (
    "ICU",
    "Medicine",
    "Surgery",
    "Emergency",
    "Pediatrics",
    "Cardiology",
    "Neurology",
    "Orthopedics",
    "Oncology",
    "Recovery",
)


def required_skill(ward: int, ordinal: int) -> int:
    """Include BLS shortages as well as ICU shortages in synthetic examples."""
    return 2 if ward % 10 == 0 else (7 if (ward + ordinal) % 3 == 0 else 4)


def counts(db: Session) -> dict[str, int]:
    return {
        "staff": db.scalar(
            select(func.count())
            .select_from(Staff)
            .where(Staff.id.between(STAFF_BASE + 1, STAFF_BASE + STAFF_COUNT))
        )
        or 0,
        "wards": db.scalar(
            select(func.count())
            .select_from(Ward)
            .where(Ward.id.between(WARD_BASE + 1, WARD_BASE + WARD_COUNT))
        )
        or 0,
        "shifts": db.scalar(
            select(func.count())
            .select_from(Shift)
            .where(Shift.id.between(SHIFT_BASE + 1, SHIFT_BASE + WARD_COUNT * DAYS * 2))
        )
        or 0,
    }


def generate(db: Session, reference_at: datetime) -> dict[str, int]:
    """Run while the caller holds the auth reset gate (shared, or exclusive on reset).

    Reset's load() supplies the original subjects through staff_subject(). Replaying
    the profile therefore never attaches a web account to a new permanent person.
    """
    if set(db.scalars(select(DemoDataset.profile))) - {PROFILE}:
        raise ValueError("Unknown demo dataset profile; import refused.")
    existing = db.scalar(select(DemoDataset).where(DemoDataset.profile == PROFILE))
    present = counts(db)
    if existing is not None:
        if present != {"staff": STAFF_COUNT, "wards": WARD_COUNT, "shifts": WARD_COUNT * DAYS * 2}:
            raise ValueError("Dataset is incomplete; refusing to overwrite existing identities.")
        return present
    if any(present.values()):
        raise ValueError("The large-demo ID namespace is occupied; nothing was changed.")
    if reference_at.tzinfo is None:
        raise ValueError("reference_at must have a timezone")
    roles = dict(db.execute(select(Role.name, Role.id)).all())
    skills = dict(db.execute(select(Skill.name, Skill.id)).all())
    if not {"RN", "HEAD_NURSE"} <= roles.keys() or not {"ICU", "BLS"} <= skills.keys():
        raise ValueError("Load the normal demo first; required roles/skills are missing.")
    system = actor_service.component_id(db, ActorName.SYSTEM)
    now = reference_at.astimezone(clock.APP_TIMEZONE)
    start_day = (now - timedelta(days=14)).replace(hour=0, minute=0, second=0, microsecond=0)
    db.add(DemoDataset(profile=PROFILE, reference_at=now))
    for ward in range(WARD_COUNT):
        db.add(
            Ward(
                id=WARD_BASE + ward + 1,
                name=f"Demo {WARD_NAMES[ward % len(WARD_NAMES)]} {ward + 1:02}",
                is_active=True,
                is_float_pool=False,
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()
    for n in range(STAFF_COUNT):
        staff_id = STAFF_BASE + n + 1
        local = n % 25
        db.add(
            Staff(
                id=staff_id,
                first_name=FIRST_NAMES[n % len(FIRST_NAMES)],
                last_name=f"จำลอง{n + 1:03}",
                email=f"mock-{staff_id}@example.invalid",
                password_hash="!",
                role_id=roles["HEAD_NURSE" if local == 24 else "RN"],
                home_ward_id=WARD_BASE + n // 25 + 1,
                status=StaffStatus.ACTIVE,
                auth_subject=staff_subject(db, staff_id),
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()
    for n in range(STAFF_COUNT):
        staff_id = STAFF_BASE + n + 1
        db.add(Actor(name=str(staff_id), actor_type=ActorType.USER, staff_id=staff_id))
        if n % 25 < 24:
            db.add(StaffSkill(staff_id=staff_id, skill_id=skills["BLS"]))
            if n % 25 % 3 == 0:
                db.add(StaffSkill(staff_id=staff_id, skill_id=skills["ICU"]))
    # One planned leave per ward, on an off-team day (no assigned row overlaps).
    for ward in range(WARD_COUNT):
        leave_start = start_day + timedelta(days=17, hours=7)
        off_team = ((17 * 2) % 4 + 2) % 4
        db.add(
            StaffUnavailability(
                staff_id=STAFF_BASE + ward * 25 + off_team * 6 + 1,
                start_at=leave_start,
                end_at=leave_start + timedelta(hours=12),
                reason=AvailabilityReason.PLANNED_LEAVE,
            )
        )
    shifts = []
    for ward in range(WARD_COUNT):
        for day in range(DAYS):
            for duty in range(2):
                index = ward * DAYS * 2 + day * 2 + duty
                start = start_day + timedelta(days=day, hours=7 + duty * 12)
                # Some future/current shifts visibly lack one RN, without starting automation.
                required = max(
                    7 if (ward + day + duty) % 7 == 0 else 6,
                    required_skill(ward, day * 2 + duty),
                )
                shift_record = Shift(
                    id=SHIFT_BASE + index + 1,
                    ward_id=WARD_BASE + ward + 1,
                    patient_count=required * 2,
                    start_at=start,
                    end_at=start + timedelta(hours=12),
                    shift_type=ShiftType.DAY if duty == 0 else ShiftType.NIGHT,
                    is_active=True,
                    merge_window_seconds=0,
                )
                db.add(shift_record)
                shifts.append((shift_record, ward, day * 2 + duty, required))
    db.flush()
    for shift, _ward, _ordinal, required in shifts:
        db.add(
            StaffingRequirement(
                id=shift.id,
                shift_id=shift.id,
                required_staff=required,
                minimum_staff=required,
                created_at=now,
            )
        )
    db.flush()
    historical = []
    for shift, ward, ordinal, required in shifts:
        db.add(
            StaffingRequirementRole(
                staffing_requirement_id=shift.id, role_id=roles["RN"], required_count=required
            )
        )
        db.add(
            StaffingRequirementSkill(
                staffing_requirement_id=shift.id,
                skill_id=skills["ICU" if ward % 10 == 0 else "BLS"],
                required_count=required_skill(ward, ordinal),
            )
        )
        past = shift.end_at <= now
        history = past and ordinal % 5 == 0
        cancelled_slot = (ordinal // 5 + ward) % 6
        rows = []
        for slot in range(6):
            staff_id = STAFF_BASE + ward * 25 + (ordinal % 4) * 6 + slot + 1
            roster_status = RosterStatus.COMPLETED if past else RosterStatus.ASSIGNED
            if history and slot == cancelled_slot:
                roster_status = RosterStatus.CANCELLED
                db.add(
                    StaffUnavailability(
                        staff_id=staff_id,
                        start_at=shift.start_at,
                        end_at=shift.end_at,
                        reason=AvailabilityReason.UNPLANNED_LEAVE,
                    )
                )
            roster_row = RosterAssignment(
                staff_id=staff_id,
                shift_id=shift.id,
                status=roster_status,
                assignment_type=AssignmentType.REGULAR,
                created_at=shift.start_at - timedelta(days=7),
                updated_at=shift.start_at,
            )
            db.add(roster_row)
            rows.append(roster_row)
            if roster_status != RosterStatus.CANCELLED and shift.start_at <= now:
                arrived = shift.start_at + timedelta(
                    minutes=5 if slot == 5 and ordinal % 5 == 0 else 0
                )
                db.add(
                    Attendance(
                        staff_id=staff_id,
                        shift_id=shift.id,
                        check_in_at=arrived,
                        check_out_at=shift.end_at if past else None,
                        work_minutes=int((shift.end_at - arrived).total_seconds() // 60)
                        if past
                        else None,
                        overtime_minutes=0 if past else None,
                        synced_at=now,
                    )
                )
        if history:
            historical.append((shift, ward, ordinal, required, rows, cancelled_slot))
    db.flush()
    # Read-only historical endpoints can show three terminal outcomes. These are
    # synthetic imports, not evidence that the live Solver/approval flow ran.
    for n, (shift, ward, ordinal, required, rows, cancelled_slot) in enumerate(historical):
        status = (CaseStatus.RESOLVED, CaseStatus.UNRESOLVED, CaseStatus.FAILED)[n % 3]
        case = StaffingCase(
            shift_id=shift.id,
            status=status,
            required_replacement_time=shift.start_at,
            created_at=shift.start_at - timedelta(minutes=30),
            updated_at=shift.end_at,
        )
        db.add(case)
        db.flush()
        event = StaffingEvent(
            event_type=EventType.STAFF_UNAVAILABLE,
            shift_id=shift.id,
            occurred_at=case.created_at,
            staff_id=rows[cancelled_slot].staff_id,
            payload={"source": "SIMULATED", "dataset": PROFILE, "synthetic_history": True},
            status=EventStatus.PROCESSED,
            processed_at=case.created_at,
            case_id=case.id,
        )
        db.add(event)
        gap = StaffingGap(
            case_id=case.id,
            staffing_requirement_id=shift.id,
            headcount_gap=max(required - 5, 0),
            effective_minimum=required,
            computed_at=shift.start_at,
            evaluated_from=shift.start_at,
        )
        db.add(gap)
        db.flush()
        db.add(
            StaffingGapRole(
                gap_id=gap.id,
                role_id=roles["RN"],
                required_count=required,
                current_count=5,
                gap_count=max(required - 5, 0),
            )
        )
        db.add(
            StaffingGapInterval(
                gap_id=gap.id,
                start_at=shift.start_at,
                end_at=shift.end_at,
                required_count=required,
                current_count=5,
                gap_count=max(required - 5, 0),
            )
        )
        db.add(
            StaffingGapRoleInterval(
                gap_id=gap.id,
                role_id=roles["RN"],
                start_at=shift.start_at,
                end_at=shift.end_at,
                required_count=required,
                current_count=5,
                gap_count=max(required - 5, 0),
            )
        )
        skill_id = skills["ICU" if ward % 10 == 0 else "BLS"]
        skill_required = required_skill(ward, ordinal)
        skill_current = (2 - int(cancelled_slot % 3 == 0)) if ward % 10 == 0 else 5
        db.add(
            StaffingGapSkill(
                gap_id=gap.id,
                skill_id=skill_id,
                required_count=skill_required,
                current_count=skill_current,
                gap_count=max(skill_required - skill_current, 0),
            )
        )
        db.add(
            StaffingGapSkillInterval(
                gap_id=gap.id,
                skill_id=skill_id,
                start_at=shift.start_at,
                end_at=shift.end_at,
                required_count=skill_required,
                current_count=skill_current,
                gap_count=max(skill_required - skill_current, 0),
            )
        )
        db.add(
            AuditLog(
                case_id=case.id,
                event_id=None,
                actor_id=system,
                entity_type=EntityType.STAFFING_CASES,
                entity_id=case.id,
                action=AuditAction.CASE_OPENED,
                payload={
                    "source": "SIMULATED",
                    "dataset": PROFILE,
                    "synthetic_history": True,
                    "final_status": status.value,
                },
                created_at=case.created_at,
            )
        )
        if status == CaseStatus.RESOLVED:
            # Off-team replacement is history only; no delivery/outreach is created.
            for slot in range(required - 5):
                relief = STAFF_BASE + ward * 25 + ((ordinal % 4 + 2) % 4) * 6 + slot + 1
                replacement = RosterAssignment(
                    staff_id=relief,
                    shift_id=shift.id,
                    status=RosterStatus.COMPLETED,
                    assignment_type=AssignmentType.REPLACEMENT,
                    created_at=case.created_at,
                    updated_at=shift.end_at,
                )
                db.add(replacement)
                db.flush()
                db.add(
                    ManualAssignment(
                        case_id=case.id,
                        roster_assignment_id=replacement.id,
                        assigned_by=STAFF_BASE + ward * 25 + 25,
                        reason="Synthetic historical import; no live workflow was run",
                        created_at=case.created_at,
                    )
                )
                db.add(
                    Attendance(
                        staff_id=relief,
                        shift_id=shift.id,
                        check_in_at=shift.start_at,
                        check_out_at=shift.end_at,
                        work_minutes=720,
                        overtime_minutes=0,
                        synced_at=now,
                    )
                )
                db.add(
                    StructuredHandover(
                        case_id=case.id,
                        shift_id=shift.id,
                        incoming_staff_id=relief,
                        roster_assignment_id=replacement.id,
                        content={
                            "version": 1,
                            "dataset": PROFILE,
                            "synthetic_history": True,
                            "case_id": case.id,
                            "shift": {
                                "id": shift.id,
                                "ward_id": shift.ward_id,
                                "ward_name": (
                                    f"Demo {WARD_NAMES[ward % len(WARD_NAMES)]} {ward + 1:02}"
                                ),
                                "start_at": shift.start_at.isoformat(),
                                "end_at": shift.end_at.isoformat(),
                            },
                            "cover_start_at": shift.start_at.isoformat(),
                            "cover_end_at": shift.end_at.isoformat(),
                            "patient_count": shift.patient_count,
                            "reason": "UNPLANNED_LEAVE",
                            "requirement": {
                                "roles": [
                                    {
                                        "role_id": roles["RN"],
                                        "role_name": "RN",
                                        "required_count": required,
                                    }
                                ],
                                "skills": [
                                    {
                                        "skill_id": skill_id,
                                        "skill_name": "ICU" if ward % 10 == 0 else "BLS",
                                        "required_count": skill_required,
                                    }
                                ],
                            },
                            "co_workers": [],
                        },
                        generated_at=case.created_at,
                        delivery_status=None,
                    )
                )
    db.flush()
    sync_sequences(
        db,
        [
            Ward.__tablename__,
            Staff.__tablename__,
            Shift.__tablename__,
            StaffingRequirement.__tablename__,
        ],
    )
    return counts(db)
