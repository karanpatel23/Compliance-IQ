from app.engine import calculate_score, run_assessment
from app.models import Facility, Regulation


def test_engine_flags_missing_programs():
    facility = Facility(
        id=1,
        name="Plant A",
        sector="all",
        state="TX",
        employees=40,
        annual_hazardous_waste_kg=500,
        stores_hazardous_chemicals=True,
        produces_human_food=False,
        has_lockout_program=False,
        has_sds_program=False,
    )
    regulation = Regulation(
        id=1,
        code="OSHA-1910.147",
        title="LOTO",
        authority="OSHA",
        applies_to_sector="all",
        criteria={"requires_lockout_program": True, "employees_gte": 1},
        required_actions=[],
        source_url="http://example.com",
        source_name="example",
        status="approved",
        version="1",
    )

    findings = run_assessment(facility, [regulation])

    assert len(findings) == 1
    assert findings[0].status == "non_compliant"
    assert calculate_score(findings) == 0.0


def test_engine_passes_when_controls_exist():
    facility = Facility(
        id=1,
        name="Plant B",
        sector="food",
        state="CA",
        employees=60,
        annual_hazardous_waste_kg=0,
        stores_hazardous_chemicals=False,
        produces_human_food=True,
        has_lockout_program=True,
        has_sds_program=True,
    )
    regulation = Regulation(
        id=2,
        code="FDA-21CFR-117",
        title="Food",
        authority="FDA",
        applies_to_sector="food",
        criteria={"produces_human_food": True},
        required_actions=[],
        source_url="http://example.com",
        source_name="example",
        status="approved",
        version="1",
    )

    findings = run_assessment(facility, [regulation])

    assert findings[0].status == "compliant"
    assert calculate_score(findings) == 100.0
