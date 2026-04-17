from dataclasses import dataclass

from .models import Facility, Regulation


@dataclass
class EngineFinding:
    regulation_id: int
    status: str
    severity: str
    details: str
    due_in_days: int


def _is_applicable(facility: Facility, regulation: Regulation) -> bool:
    if regulation.applies_to_sector != "all" and facility.sector.lower() != regulation.applies_to_sector.lower():
        return False

    criteria = regulation.criteria
    if criteria.get("employees_gte") is not None and facility.employees < criteria["employees_gte"]:
        return False
    if criteria.get("annual_hazardous_waste_kg_gt") is not None and (
        facility.annual_hazardous_waste_kg <= criteria["annual_hazardous_waste_kg_gt"]
    ):
        return False
    if criteria.get("stores_hazardous_chemicals") and not facility.stores_hazardous_chemicals:
        return False
    if criteria.get("produces_human_food") and not facility.produces_human_food:
        return False
    return True


def run_assessment(facility: Facility, regulations: list[Regulation]) -> list[EngineFinding]:
    findings: list[EngineFinding] = []
    for regulation in regulations:
        if regulation.status != "approved":
            continue
        if not _is_applicable(facility, regulation):
            continue

        criteria = regulation.criteria
        gaps: list[str] = []
        if criteria.get("requires_lockout_program") and not facility.has_lockout_program:
            gaps.append("Lockout/tagout program is missing or incomplete.")
        if criteria.get("requires_sds_program") and not facility.has_sds_program:
            gaps.append("SDS / hazard communication program is missing or incomplete.")

        if gaps:
            findings.append(
                EngineFinding(
                    regulation_id=regulation.id,
                    status="non_compliant",
                    severity="high",
                    details=" ".join(gaps),
                    due_in_days=30,
                )
            )
        else:
            findings.append(
                EngineFinding(
                    regulation_id=regulation.id,
                    status="compliant",
                    severity="low",
                    details="Required controls appear in place based on submitted profile.",
                    due_in_days=0,
                )
            )
    return findings


def calculate_score(findings: list[EngineFinding]) -> float:
    if not findings:
        return 100.0
    compliant = sum(1 for f in findings if f.status == "compliant")
    return round((compliant / len(findings)) * 100, 2)
