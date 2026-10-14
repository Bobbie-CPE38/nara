"""Errors that more than one layer raises or handles."""


class CaseNotFoundError(LookupError):
    """No STAFFING_CASES row has this ID."""


class ShiftNotFoundError(LookupError):
    """No SHIFT row has this ID."""


class StaffNotFoundError(LookupError):
    """No STAFF row has this ID."""
