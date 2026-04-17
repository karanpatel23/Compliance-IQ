from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _signup_and_authenticate():
    response = client.post(
        "/signup",
        data={
            "full_name": "Admin User",
            "email": "admin@example.com",
            "company_name": "Demo Co",
            "role": "admin",
            "password": "password123",
        },
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)


def test_public_pages_available():
    assert client.get("/").status_code in (200, 302)
    assert client.get("/signup").status_code == 200
    assert client.get("/signin").status_code == 200


def test_regulation_workflow_and_assessment():
    _signup_and_authenticate()

    facility_resp = client.post(
        "/facilities",
        json={
            "name": "Demo Manufacturing",
            "sector": "food",
            "state": "OH",
            "employees": 40,
            "annual_hazardous_waste_kg": 250,
            "stores_hazardous_chemicals": True,
            "produces_human_food": True,
            "has_lockout_program": False,
            "has_sds_program": False,
        },
    )
    assert facility_resp.status_code == 200

    stale_resp = client.get("/regulations/stale")
    assert stale_resp.status_code == 200

    facility_id = facility_resp.json()["id"]

    assessment_resp = client.post("/assessments/run", json={"facility_id": facility_id})
    assert assessment_resp.status_code == 200
    data = assessment_resp.json()
    assert data["facility_id"] == facility_id
    assert len(data["findings"]) >= 1

    csv_resp = client.get(f"/reports/assessment/{data['assessment_id']}/csv")
    assert csv_resp.status_code == 200
    assert "regulation_code" in csv_resp.text


def test_readiness_checklist_available():
    response = client.get("/readiness/checklist")
    assert response.status_code == 200
    assert "implemented" in response.json()
