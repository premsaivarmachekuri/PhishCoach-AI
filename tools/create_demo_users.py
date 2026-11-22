"""Create demo user accounts in DuckDB for Employee (treatment/control), Security Admin, and HR Viewer."""
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.anonymizer import make_anon_id
from app.services.auth import hash_password
from app.services.db import get_db

DEMO_ACCOUNTS = [
    ("asha.treatment@example.com", "DemoPass123!", "Finance Analyst", "Finance", "treatment", "employee"),
    ("dev.control@example.com", "DemoPass123!", "Software Engineer", "Engineering", "control", "employee"),
    ("ravi.admin@example.com", "DemoPass123!", "Security Admin", "IT", "treatment", "security_admin"),
    ("meera.hr@example.com", "DemoPass123!", "HR Director", "HR", "control", "hr_viewer"),
]


def main() -> None:
    load_dotenv()
    db = get_db()

    for email, password, role_name, dept, arm, app_role in DEMO_ACCOUNTS:
        norm_email = email.strip().lower()
        existing_acct = db.select("auth_accounts", filters={"email": norm_email}, limit=1)
        if existing_acct:
            auth_uid = existing_acct[0]["id"]
            db.update("auth_accounts", {"password_hash": hash_password(password)}, {"id": auth_uid})
        else:
            auth_uid = str(uuid.uuid4())
            db.insert(
                "auth_accounts",
                {"id": auth_uid, "email": norm_email, "password_hash": hash_password(password)},
            )

        anon_id = make_anon_id(norm_email)
        db.upsert(
            "users",
            {
                "anon_id": anon_id,
                "role_name": role_name,
                "department": dept,
                "seniority": "mid",
                "arm": arm,
                "app_role": app_role,
                "is_synthetic": False,
                "auth_user_id": auth_uid,
            },
            on_conflict="anon_id",
        )
        print(f"Ready: {norm_email} ({app_role}, {arm}) -> {anon_id}")


if __name__ == "__main__":
    main()
