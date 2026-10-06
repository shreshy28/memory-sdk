from fastapi.testclient import TestClient
from memory_api import create_app as create_api
from memory_domain import ComponentStatus, HealthReport
from memory_worker import create_app as create_worker


class ReadyProbe:
    async def check(self) -> HealthReport:
        return HealthReport(
            status=ComponentStatus.READY,
            checks={"database": ComponentStatus.READY, "migrations": ComponentStatus.READY},
        )


class UnavailableProbe:
    async def check(self) -> HealthReport:
        return HealthReport(
            status=ComponentStatus.NOT_READY,
            checks={"database": ComponentStatus.NOT_READY},
        )


def test_api_liveness_does_not_require_dependencies() -> None:
    with TestClient(create_api(UnavailableProbe())) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive", "checks": None}


def test_api_readiness_reports_dependency_state() -> None:
    with TestClient(create_api(ReadyProbe())) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["checks"] == {"database": "ready", "migrations": "ready"}


def test_api_readiness_fails_when_dependency_is_unavailable() -> None:
    with TestClient(create_api(UnavailableProbe())) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_worker_readiness_includes_lease_capability() -> None:
    with TestClient(create_worker(ReadyProbe())) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["checks"]["lease"] == "ready"
