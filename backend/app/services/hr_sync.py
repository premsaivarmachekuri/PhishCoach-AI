"""HR directory sync shared by the API endpoint and tools/sync_hr.py."""
from typing import Any

from app.adapters.hr import HRAdapter
from app.services.anonymizer import make_anon_id
from app.services.db import DBProtocol


async def sync_employees(db: DBProtocol, hr_adapter: HRAdapter) -> dict[str, Any]:
    employees = await hr_adapter.fetch_employees()
    existing = {u["anon_id"]: u for u in db.select("users")}
    n_treatment = sum(1 for u in existing.values() if u["arm"] == "treatment" and u["app_role"] == "employee")
    n_control = sum(1 for u in existing.values() if u["arm"] == "control" and u["app_role"] == "employee")

    created = updated = 0
    for emp in employees:
        ext_id = str(emp.get("employee_id") or emp.get("id"))
        anon_id = make_anon_id(ext_id)
        fields: dict[str, Any] = {
            "anon_id": anon_id,
            "role_name": emp.get("role_name", "Analyst"),
            "department": emp.get("department", "Operations"),
            "seniority": emp.get("seniority", "mid"),
        }
        if anon_id in existing:
            updated += 1  # arm, app_role and synthetic flag are never changed by an external feed
        else:
            # Keep arms balanced by always assigning to the currently smaller arm.
            arm = "treatment" if n_treatment <= n_control else "control"
            if arm == "treatment":
                n_treatment += 1
            else:
                n_control += 1
            # The HR feed can never mint privileged accounts: new users are always plain employees.
            fields.update({"arm": arm, "app_role": "employee", "is_synthetic": False})
            created += 1
        db.upsert("users", fields, on_conflict="anon_id")
    return {"fetched": len(employees), "created": created, "updated": updated}
