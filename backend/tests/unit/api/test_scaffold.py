"""The step 4 scaffold: every router is registered once, and shared errors map to HTTP codes."""

from types import ModuleType

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.api.exception_handlers import register_exception_handlers
from app.api.routes import approvals, cases, demo, events, line_sim, roster
from app.domain.enums import CaseStatus
from app.domain.errors import CaseNotFoundError
from app.domain.workflow.transitions import InvalidTransitionError, assert_transition
from app.main import app
from app.services.actor_service import ActorNotFoundError

ROUTERS: list[tuple[ModuleType, str]] = [
    (demo, "/demo"),
    (events, "/events"),
    (cases, "/cases"),
    (approvals, "/approvals"),
    (roster, "/roster"),
    (line_sim, "/demo/line-sim"),
]


def _paths(application: FastAPI) -> set[str]:
    # The OpenAPI document, not application.routes: FastAPI keeps an included
    # router as one nested entry there, without its paths
    return set(application.openapi()["paths"])


@pytest.mark.parametrize(("module", "prefix"), ROUTERS, ids=[prefix for _, prefix in ROUTERS])
def test_router_prefix_matches_the_api_table(module: ModuleType, prefix: str) -> None:
    """Prefixes from docs/workflow.md section 9. line-sim keeps its /demo URLs."""
    assert module.router.prefix == prefix


@pytest.mark.parametrize(("module", "prefix"), ROUTERS, ids=[prefix for _, prefix in ROUTERS])
def test_every_route_of_a_router_is_served_by_the_app(module: ModuleType, prefix: str) -> None:
    """Fails when a router module exists but main.py does not include it.

    Empty routers pass trivially today. The check starts to bite as soon as
    step 4 adds the first route to a file. It compares paths from the OpenAPI
    document only: not the HTTP method, and not routes hidden from the schema.
    """
    module_paths = {route.path for route in module.router.routes if isinstance(route, APIRoute)}

    assert module_paths <= _paths(app)


def test_demo_reset_is_still_served() -> None:
    assert "/demo/reset" in _paths(app)


@pytest.mark.parametrize("error_type", [InvalidTransitionError, CaseNotFoundError])
def test_main_registers_the_shared_exception_handlers(error_type: type[Exception]) -> None:
    assert error_type in app.exception_handlers


@pytest.fixture
def client() -> TestClient:
    throwaway = FastAPI()
    register_exception_handlers(throwaway)

    @throwaway.get("/repeated-request")
    def repeated_request() -> None:
        # What orchestrator.resume() raises for a second ACCEPT
        assert_transition(CaseStatus.WAITING_APPROVAL, CaseStatus.SAFETY_VALIDATION)

    @throwaway.get("/missing-case")
    def missing_case() -> None:
        raise CaseNotFoundError("No case 999")

    @throwaway.get("/missing-actor")
    def missing_actor() -> None:
        raise ActorNotFoundError("No actor named 'workflow_orchestrator'")

    return TestClient(throwaway, raise_server_exceptions=False)


def test_invalid_transition_answers_409(client: TestClient) -> None:
    response = client.get("/repeated-request")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Invalid case transition: WAITING_APPROVAL -> SAFETY_VALIDATION"
    }


def test_case_not_found_answers_404(client: TestClient) -> None:
    response = client.get("/missing-case")

    assert response.status_code == 404
    assert response.json() == {"detail": "No case 999"}


def test_other_lookup_errors_stay_500(client: TestClient) -> None:
    """A missing actor means broken seed data, not a bad request."""
    response = client.get("/missing-actor")

    assert response.status_code == 500


def test_case_not_found_error_is_still_reachable_through_the_orchestrator() -> None:
    """Other branches raise orchestrator.CaseNotFoundError. It must stay the same class,
    or the shared 404 handler would not catch what they raise."""
    from app.workflow import orchestrator

    assert orchestrator.CaseNotFoundError is CaseNotFoundError
