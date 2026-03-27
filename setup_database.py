import random
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path


DB_PATH = Path(__file__).with_name("clinic.db")


def _random_date_within_last_days(days: int) -> date:
    start = date.today() - timedelta(days=days)
    return start + timedelta(days=random.randint(0, days))


def _random_datetime_within_last_days(days: int) -> datetime:
    d = _random_date_within_last_days(days)
    hour = random.randint(8, 18)
    minute = random.choice([0, 15, 30, 45])
    return datetime(d.year, d.month, d.day, hour, minute)


FIRST_NAMES_M = [
    "Aarav",
    "Vivaan",
    "Aditya",
    "Arjun",
    "Sai",
    "Krishna",
    "Ishaan",
    "Rohan",
    "Rahul",
    "Karthik",
    "Pranav",
    "Nikhil",
    "Vikram",
    "Manish",
    "Siddharth",
    "Aniket",
    "Aman",
    "Harsh",
    "Yash",
    "Deepak",
]
FIRST_NAMES_F = [
    "Ananya",
    "Aadhya",
    "Diya",
    "Myra",
    "Ira",
    "Saanvi",
    "Kavya",
    "Pooja",
    "Priya",
    "Neha",
    "Sneha",
    "Riya",
    "Nisha",
    "Meera",
    "Asha",
    "Ishita",
    "Tanvi",
    "Swati",
    "Shreya",
    "Divya",
]
LAST_NAMES = [
    "Sharma",
    "Verma",
    "Gupta",
    "Patel",
    "Singh",
    "Kumar",
    "Reddy",
    "Iyer",
    "Nair",
    "Rao",
    "Bose",
    "Chopra",
    "Mehta",
    "Agarwal",
    "Mishra",
    "Joshi",
    "Yadav",
    "Kulkarni",
    "Desai",
    "Kapoor",
    "Bhat",
    "Pandey",
    "Saxena",
    "Tiwari",
]

CITIES = [
    "Mumbai",
    "Delhi",
    "Bengaluru",
    "Hyderabad",
    "Chennai",
    "Kolkata",
    "Pune",
    "Ahmedabad",
    "Jaipur",
    "Lucknow",
]


@dataclass(frozen=True)
class Counts:
    patients: int
    doctors: int
    appointments: int
    treatments: int
    invoices: int


def create_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON;")

    conn.executescript(
        """
        DROP TABLE IF EXISTS treatments;
        DROP TABLE IF EXISTS appointments;
        DROP TABLE IF EXISTS invoices;
        DROP TABLE IF EXISTS doctors;
        DROP TABLE IF EXISTS patients;

        CREATE TABLE patients (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          first_name TEXT NOT NULL,
          last_name TEXT NOT NULL,
          email TEXT,
          phone TEXT,
          date_of_birth DATE,
          gender TEXT,
          city TEXT,
          registered_date DATE
        );

        CREATE TABLE doctors (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          specialization TEXT,
          department TEXT,
          phone TEXT
        );

        CREATE TABLE appointments (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          patient_id INTEGER,
          doctor_id INTEGER,
          appointment_date DATETIME,
          status TEXT,
          notes TEXT,
          FOREIGN KEY(patient_id) REFERENCES patients(id),
          FOREIGN KEY(doctor_id) REFERENCES doctors(id)
        );

        CREATE TABLE treatments (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          appointment_id INTEGER,
          treatment_name TEXT,
          cost REAL,
          duration_minutes INTEGER,
          FOREIGN KEY(appointment_id) REFERENCES appointments(id)
        );

        CREATE TABLE invoices (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          patient_id INTEGER,
          invoice_date DATE,
          total_amount REAL,
          paid_amount REAL,
          status TEXT,
          FOREIGN KEY(patient_id) REFERENCES patients(id)
        );

        CREATE INDEX idx_patients_city ON patients(city);
        CREATE INDEX idx_appointments_date ON appointments(appointment_date);
        CREATE INDEX idx_appointments_doctor ON appointments(doctor_id);
        CREATE INDEX idx_appointments_patient ON appointments(patient_id);
        CREATE INDEX idx_invoices_patient ON invoices(patient_id);
        """
    )


def _maybe_null(value: str, p_null: float) -> str | None:
    return None if random.random() < p_null else value


def _indian_mobile() -> str:
    return f"+91-{random.randint(60000, 99999)}-{random.randint(10000, 99999)}"


def insert_doctors(conn: sqlite3.Connection) -> int:
    specializations = [
        ("Dermatology", "Skin"),
        ("Cardiology", "Heart"),
        ("Orthopedics", "Bones"),
        ("General", "General Medicine"),
        ("Pediatrics", "Children"),
    ]
    doctor_rows: list[tuple[str, str, str, str | None]] = []
    for i in range(15):
        spec, dept = specializations[i % len(specializations)]
        first = random.choice(FIRST_NAMES_M + FIRST_NAMES_F)
        last = random.choice(LAST_NAMES)
        name = f"Dr. {first} {last}"
        phone = _maybe_null(_indian_mobile(), 0.1)
        doctor_rows.append((name, spec, dept, phone))

    conn.executemany(
        "INSERT INTO doctors (name, specialization, department, phone) VALUES (?, ?, ?, ?)",
        doctor_rows,
    )
    return len(doctor_rows)


def insert_patients(conn: sqlite3.Connection) -> int:
    patient_rows: list[tuple[str, str, str | None, str | None, str, str, str, str]] = []
    for _ in range(200):
        gender = random.choice(["M", "F"])
        first = random.choice(FIRST_NAMES_M if gender == "M" else FIRST_NAMES_F)
        last = random.choice(LAST_NAMES)

        base_email = f"{first}.{last}{random.randint(1, 999)}".lower()
        email = _maybe_null(f"{base_email}@example.com", 0.2)
        phone = _maybe_null(_indian_mobile(), 0.15)

        dob = date.today() - timedelta(days=random.randint(18 * 365, 85 * 365))
        city = random.choice(CITIES)
        registered = _random_date_within_last_days(365)
        patient_rows.append((first, last, email, phone, str(dob), gender, city, str(registered)))

    conn.executemany(
        """
        INSERT INTO patients (first_name, last_name, email, phone, date_of_birth, gender, city, registered_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        patient_rows,
    )
    return len(patient_rows)


def _weighted_choice(items: list[int], weights: list[float]) -> int:
    # random.choices is fine, but this keeps it explicit for reproducibility.
    return random.choices(items, weights=weights, k=1)[0]


def insert_appointments(conn: sqlite3.Connection) -> int:
    patient_ids = [row[0] for row in conn.execute("SELECT id FROM patients").fetchall()]
    doctor_ids = [row[0] for row in conn.execute("SELECT id FROM doctors").fetchall()]

    # Some patients are repeat visitors.
    patient_weights = []
    for pid in patient_ids:
        # 15% heavy users, 35% medium, 50% light
        r = random.random()
        if r < 0.15:
            patient_weights.append(6.0)
        elif r < 0.50:
            patient_weights.append(2.5)
        else:
            patient_weights.append(1.0)

    # Some doctors are busier.
    doctor_weights = []
    for _ in doctor_ids:
        doctor_weights.append(random.uniform(0.7, 2.2))

    statuses = ["Scheduled", "Completed", "Cancelled", "No-Show"]
    status_weights = [0.25, 0.55, 0.12, 0.08]

    appointment_rows: list[tuple[int, int, str, str, str | None]] = []
    for _ in range(500):
        patient_id = _weighted_choice(patient_ids, patient_weights)
        doctor_id = _weighted_choice(doctor_ids, doctor_weights)
        dt = _random_datetime_within_last_days(365)
        status = random.choices(statuses, weights=status_weights, k=1)[0]
        notes = _maybe_null(
            random.choice(
                [
                    "Follow-up after 2 weeks",
                    "Patient reported knee pain",
                    "Blood tests advised",
                    "Medicines prescribed for 5 days",
                    "Referred to senior consultant",
                ]
            ),
            0.55,
        )
        appointment_rows.append((patient_id, doctor_id, dt.isoformat(sep=" "), status, notes))

    conn.executemany(
        """
        INSERT INTO appointments (patient_id, doctor_id, appointment_date, status, notes)
        VALUES (?, ?, ?, ?, ?)
        """,
        appointment_rows,
    )
    return len(appointment_rows)


def insert_treatments(conn: sqlite3.Connection) -> int:
    completed_appointments = [
        row[0]
        for row in conn.execute("SELECT id FROM appointments WHERE status = 'Completed'").fetchall()
    ]
    random.shuffle(completed_appointments)
    target = min(350, len(completed_appointments))
    chosen = completed_appointments[:target]

    treatments = [
        "Consultation",
        "X-Ray",
        "Blood Test",
        "MRI Scan",
        "Physical Therapy",
        "Skin Biopsy",
        "ECG",
        "Vaccination",
        "Casting",
        "Wound Dressing",
    ]

    rows: list[tuple[int, str, float, int]] = []
    for appt_id in chosen:
        name = random.choice(treatments)
        cost = round(random.uniform(50, 5000), 2)
        duration = random.choice([15, 20, 30, 45, 60, 75, 90, 120])
        rows.append((appt_id, name, cost, duration))

    conn.executemany(
        """
        INSERT INTO treatments (appointment_id, treatment_name, cost, duration_minutes)
        VALUES (?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


def insert_invoices(conn: sqlite3.Connection) -> int:
    patient_ids = [row[0] for row in conn.execute("SELECT id FROM patients").fetchall()]
    statuses = ["Paid", "Pending", "Overdue"]
    status_weights = [0.6, 0.25, 0.15]

    rows: list[tuple[int, str, float, float, str]] = []
    for _ in range(300):
        pid = random.choice(patient_ids)
        inv_date = _random_date_within_last_days(365)
        total = round(random.uniform(80, 8000), 2)
        status = random.choices(statuses, weights=status_weights, k=1)[0]
        if status == "Paid":
            paid = total
        elif status == "Pending":
            paid = round(total * random.uniform(0.0, 0.6), 2)
        else:  # Overdue
            paid = round(total * random.uniform(0.0, 0.3), 2)
        rows.append((pid, str(inv_date), total, paid, status))

    conn.executemany(
        """
        INSERT INTO invoices (patient_id, invoice_date, total_amount, paid_amount, status)
        VALUES (?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def setup_database(db_path: Path = DB_PATH) -> Counts:
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    try:
        create_schema(conn)
        doctors = insert_doctors(conn)
        patients = insert_patients(conn)
        appointments = insert_appointments(conn)
        treatments = insert_treatments(conn)
        invoices = insert_invoices(conn)
        conn.commit()

        # Sanity counts from DB
        return Counts(
            patients=_count(conn, "patients"),
            doctors=_count(conn, "doctors"),
            appointments=_count(conn, "appointments"),
            treatments=_count(conn, "treatments"),
            invoices=_count(conn, "invoices"),
        )
    finally:
        conn.close()


def main() -> None:
    random.seed(42)
    counts = setup_database(DB_PATH)
    print(
        f"Created {counts.patients} patients, {counts.doctors} doctors, "
        f"{counts.appointments} appointments, {counts.treatments} treatments, "
        f"{counts.invoices} invoices."
    )
    print(f"Database path: {DB_PATH}")


if __name__ == "__main__":
    main()
