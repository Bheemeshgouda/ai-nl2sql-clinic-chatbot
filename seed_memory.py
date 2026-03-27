from dataclasses import dataclass
from typing import Any

from vanna.core.user import RequestContext, User


@dataclass(frozen=True)
class SeedPair:
    question: str
    sql: str


SEEDS: list[SeedPair] = [
    # Patient queries
    SeedPair("How many patients do we have?", "SELECT COUNT(*) AS total_patients FROM patients"),
    SeedPair(
        "List female patients in Springfield",
        "SELECT id, first_name, last_name, city, gender FROM patients WHERE city = 'Springfield' AND gender = 'F' ORDER BY last_name, first_name",
    ),
    SeedPair(
        "List patients registered in the last 3 months",
        "SELECT id, first_name, last_name, registered_date FROM patients WHERE registered_date >= date('now','-3 months') ORDER BY registered_date DESC",
    ),
    SeedPair(
        "Which city has the most patients?",
        "SELECT city, COUNT(*) AS patient_count FROM patients GROUP BY city ORDER BY patient_count DESC LIMIT 1",
    ),
    # Doctor queries
    SeedPair(
        "List all doctors and their specializations",
        "SELECT id, name, specialization, department FROM doctors ORDER BY name",
    ),
    SeedPair(
        "Which doctor has the most appointments?",
        "SELECT d.name, COUNT(*) AS appointment_count FROM appointments a JOIN doctors d ON d.id = a.doctor_id GROUP BY d.id, d.name ORDER BY appointment_count DESC LIMIT 1",
    ),
    SeedPair(
        "Show appointments per doctor",
        "SELECT d.name, COUNT(*) AS appointment_count FROM appointments a JOIN doctors d ON d.id = a.doctor_id GROUP BY d.id, d.name ORDER BY appointment_count DESC",
    ),
    # Appointment queries
    SeedPair(
        "Show me appointments for last month",
        "SELECT a.id, a.appointment_date, a.status, p.first_name, p.last_name, d.name AS doctor_name FROM appointments a JOIN patients p ON p.id = a.patient_id JOIN doctors d ON d.id = a.doctor_id WHERE a.appointment_date >= datetime('now','start of month','-1 month') AND a.appointment_date < datetime('now','start of month') ORDER BY a.appointment_date DESC",
    ),
    SeedPair(
        "How many cancelled appointments last quarter?",
        "SELECT COUNT(*) AS cancelled_appointments FROM appointments WHERE status = 'Cancelled' AND appointment_date >= datetime('now','start of month','-3 months')",
    ),
    SeedPair(
        "Show monthly appointment count for the past 6 months",
        "SELECT strftime('%Y-%m', appointment_date) AS month, COUNT(*) AS appointment_count FROM appointments WHERE appointment_date >= datetime('now','-6 months') GROUP BY month ORDER BY month",
    ),
    SeedPair(
        "What percentage of appointments are no-shows?",
        "SELECT ROUND(100.0 * SUM(CASE WHEN status = 'No-Show' THEN 1 ELSE 0 END) / COUNT(*), 2) AS no_show_percentage FROM appointments",
    ),
    SeedPair(
        "Show the busiest day of the week for appointments",
        "SELECT CASE strftime('%w', appointment_date) WHEN '0' THEN 'Sunday' WHEN '1' THEN 'Monday' WHEN '2' THEN 'Tuesday' WHEN '3' THEN 'Wednesday' WHEN '4' THEN 'Thursday' WHEN '5' THEN 'Friday' WHEN '6' THEN 'Saturday' END AS weekday, COUNT(*) AS appointment_count FROM appointments GROUP BY strftime('%w', appointment_date) ORDER BY appointment_count DESC LIMIT 1",
    ),
    # Financial queries
    SeedPair("What is the total revenue?", "SELECT SUM(total_amount) AS total_revenue FROM invoices"),
    SeedPair(
        "Show unpaid invoices",
        "SELECT id, patient_id, invoice_date, total_amount, paid_amount, status FROM invoices WHERE status IN ('Pending','Overdue') ORDER BY invoice_date DESC",
    ),
    SeedPair(
        "Top 5 patients by spending",
        "SELECT p.id, p.first_name, p.last_name, SUM(i.total_amount) AS total_spending FROM invoices i JOIN patients p ON p.id = i.patient_id GROUP BY p.id, p.first_name, p.last_name ORDER BY total_spending DESC LIMIT 5",
    ),
    # Multi-table (treatments + specialization)
    SeedPair(
        "Average treatment cost by specialization",
        "SELECT d.specialization, AVG(t.cost) AS avg_treatment_cost FROM treatments t JOIN appointments a ON a.id = t.appointment_id JOIN doctors d ON d.id = a.doctor_id GROUP BY d.specialization ORDER BY avg_treatment_cost DESC",
    ),
]


def _get_tool_context_fallback(agent: Any) -> Any:
    """
    DemoAgentMemory expects a ToolContext; its import path has changed across versions.
    We try a few common locations; as a last resort we create a minimal stub.
    """
    user = User(id="default_user", email="default_user@example.com", group_memberships=["admin", "user"])
    rc = RequestContext()

    for path, name in [
        ("vanna.core.tool_context", "ToolContext"),
        ("vanna.core.tools.context", "ToolContext"),
        ("vanna.core.tool", "ToolContext"),
        ("vanna.core.types", "ToolContext"),
    ]:
        try:
            mod = __import__(path, fromlist=[name])
            ToolContext = getattr(mod, name)
            # Many ToolContext classes accept (request_context, user, agent)
            try:
                return ToolContext(request_context=rc, user=user, agent=agent)
            except TypeError:
                try:
                    return ToolContext(request_context=rc, user=user)
                except TypeError:
                    return ToolContext()
        except Exception:
            continue

    class _StubToolContext:
        def __init__(self) -> None:
            self.request_context = rc
            self.user = user
            self.agent = agent

    return _StubToolContext()

async def seed_agent_memory(agent: Any) -> int:
    memory = getattr(agent, "agent_memory", None)
    if memory is None:
        raise RuntimeError("Agent has no agent_memory attached.")

    ctx = _get_tool_context_fallback(agent)

    saved = 0
    for pair in SEEDS:
        # Preferred: Vanna 2.0 memory interface (async)
        if hasattr(memory, "save_tool_usage"):
            await memory.save_tool_usage(
                question=pair.question,
                # Match the default tool name used by Vanna for RunSqlTool.
                tool_name="run_sql",
                args={"sql": pair.sql},
                context=ctx,
                success=True,
            )
            saved += 1
        # Fallback: some versions store a list internally
        elif hasattr(memory, "items") and isinstance(memory.items, list):
            memory.items.append(
                {"question": pair.question, "tool_name": "run_sql", "args": {"sql": pair.sql}, "success": True}
            )
            saved += 1
        else:
            raise RuntimeError("Unsupported DemoAgentMemory API; cannot seed memory.")

    return saved


def main() -> None:
    import asyncio

    from vanna_setup import create_agent

    agent = create_agent()
    saved = asyncio.run(seed_agent_memory(agent))
    print(f"Seeded agent memory with {saved} question–SQL pairs.")


if __name__ == "__main__":
    main()

