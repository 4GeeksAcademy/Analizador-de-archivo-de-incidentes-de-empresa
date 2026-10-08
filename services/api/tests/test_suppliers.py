import pytest
from fastapi.testclient import TestClient
from pathlib import Path

from services.api.app import create_app
from services.api.seed import seed_suppliers


@pytest.fixture
def api_client(tmp_path):
    app = create_app(tmp_path / "runtime" / "suppliers.json")
    with TestClient(app) as client:
        yield client


def create_payload(**overrides):
    payload = {
        "name": "New Supplier",
        "country": "Spain",
        "categories": ["ats_software"],
        "monthly_rate": 125.5,
        "currency": "EUR",
        "status": "active",
        "contract_renewal_date": "2027-05-30",
        "contact_email": "contact@example.com",
        "notes": "Test supplier",
    }
    payload.update(overrides)
    return payload


def test_startup_seeds_exactly_15_and_restarts_without_resetting_edits(tmp_path):
    database = tmp_path / "runtime" / "suppliers.json"
    app = create_app(database)
    with TestClient(app) as client:
        response = client.get("/api/suppliers")
        suppliers = response.json()
        assert response.status_code == 200
        assert len(suppliers) == 15
        assert suppliers[0]["name"] == "LinkedIn Talent Solutions"
        supplier_id = suppliers[0]["id"]
        changed = client.patch(f"/api/suppliers/{supplier_id}", json={"monthly_rate": 1300})
        assert changed.status_code == 200

    with TestClient(create_app(database)) as client:
        suppliers = client.get("/api/suppliers").json()
        assert len(suppliers) == 15
        assert next(item for item in suppliers if item["id"] == supplier_id)["monthly_rate"] == 1300


def test_seed_command_reports_insert_count_and_is_idempotent(tmp_path):
    database = tmp_path / "runtime" / "suppliers.json"

    assert seed_suppliers(database) == (15, 15)
    assert seed_suppliers(database) == (0, 15)


def test_incident_analyzer_remains_available(api_client):
    fixture_path = Path(__file__).resolve().parents[3] / "scripts" / "incidents-nexova.csv"

    with fixture_path.open("rb") as fixture:
        response = api_client.post(
            "/api/incidents/analyze",
            files={"file": (fixture_path.name, fixture, "text/csv")},
        )

    assert response.status_code == 200
    assert response.json()["valid"] == 96


@pytest.mark.parametrize(
    "overrides",
    [
        {"country": "Canada"},
        {"categories": []},
        {"categories": ["unknown_category"]},
        {"monthly_rate": 0},
        {"currency": "USD"},
        {"status": "pending"},
        {"contract_renewal_date": "2027-02-30"},
        {"contact_email": "not-an-email"},
        {"updated_at": "2026-10-08T00:00:00Z"},
    ],
)
def test_invalid_supplier_is_rejected_without_write(api_client, overrides):
    response = api_client.post("/api/suppliers", json=create_payload(**overrides))

    assert response.status_code == 422
    suppliers = api_client.get("/api/suppliers").json()
    assert len(suppliers) == 15
    assert all(supplier["name"] != "New Supplier" for supplier in suppliers)


def test_missing_country_is_rejected_without_write(api_client):
    payload = create_payload()
    del payload["country"]

    response = api_client.post("/api/suppliers", json=payload)

    assert response.status_code == 422
    assert len(api_client.get("/api/suppliers").json()) == 15


def test_country_and_category_filters_compose(api_client):
    response = api_client.get("/api/suppliers", params={"country": "Spain", "category": "ats_software"})

    assert response.status_code == 200
    assert [supplier["name"] for supplier in response.json()] == ["Workable"]


def test_create_get_rate_update_and_status_update(api_client):
    created = api_client.post("/api/suppliers", json=create_payload())
    assert created.status_code == 201
    supplier = created.json()
    assert supplier["updated_at"]

    detail = api_client.get(f"/api/suppliers/{supplier['id']}")
    assert detail.status_code == 200

    rate_update = api_client.patch(
        f"/api/suppliers/{supplier['id']}",
        json={"monthly_rate": 150},
    )
    assert rate_update.status_code == 200
    assert rate_update.json()["monthly_rate"] == 150
    assert rate_update.json()["updated_at"] != supplier["updated_at"]

    suspended = api_client.patch(f"/api/suppliers/{supplier['id']}", json={"status": "suspended"})
    assert suspended.status_code == 200
    assert suspended.json()["status"] == "suspended"
    assert suspended.json()["updated_at"] == rate_update.json()["updated_at"]


def test_unknown_supplier_and_delete_are_not_supported(api_client):
    supplier_id = "00000000-0000-0000-0000-000000000000"

    assert api_client.get(f"/api/suppliers/{supplier_id}").status_code == 404
    assert api_client.patch(f"/api/suppliers/{supplier_id}", json={"status": "active"}).status_code == 404
    assert api_client.delete(f"/api/suppliers/{supplier_id}").status_code == 405


@pytest.mark.parametrize(
    "changes",
    [
        {"monthly_rate": 100, "status": None},
        {"monthly_rate": None, "status": "suspended"},
    ],
)
def test_null_patch_values_are_rejected_without_mutation(api_client, changes):
    original = api_client.get("/api/suppliers").json()[0]

    response = api_client.patch(f"/api/suppliers/{original['id']}", json=changes)

    assert response.status_code == 422
    unchanged = api_client.get(f"/api/suppliers/{original['id']}").json()
    assert unchanged["monthly_rate"] == original["monthly_rate"]
    assert unchanged["status"] == original["status"]