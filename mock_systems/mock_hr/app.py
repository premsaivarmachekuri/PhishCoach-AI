from faker import Faker
from fastapi import FastAPI

app = FastAPI(title="Mock HR Service", version="1.0.0")

fake = Faker()
Faker.seed(42)

DEPARTMENTS = [
    ("Finance", ["Finance Analyst", "Accounts Payable Specialist", "Controller"]),
    ("Engineering", ["Software Engineer", "DevOps Engineer", "QA Lead"]),
    ("IT", ["Helpdesk Technician", "Systems Administrator", "IT Manager"]),
    ("HR", ["HR Coordinator", "Recruiter", "People Partner"]),
    ("Sales", ["Account Executive", "Sales Operations", "Regional Manager"]),
    ("Operations", ["Operations Coordinator", "Procurement Lead", "Facilities Manager"]),
]

_EMPLOYEES: list[dict] = []


def _generate_employees(count: int = 36) -> list[dict]:
    if _EMPLOYEES:
        return _EMPLOYEES
    for i in range(count):
        dept, roles = DEPARTMENTS[i % len(DEPARTMENTS)]
        role = roles[i % len(roles)]
        _EMPLOYEES.append(
            {
                "employee_id": f"HR-{1000 + i}",
                "full_name": fake.name(),
                "email": fake.company_email(),
                "department": dept,
                "role_name": role,
                "seniority": ["junior", "mid", "senior"][i % 3],
                "app_role": "employee",
                "is_synthetic": False,
            }
        )
    return _EMPLOYEES


@app.on_event("startup")
def startup_event():
    _generate_employees()


@app.get("/health")
def health():
    return {"status": "ok", "service": "mock-hr"}


@app.get("/mock/hr/employees")
def list_employees():
    return {"employees": _generate_employees()}
