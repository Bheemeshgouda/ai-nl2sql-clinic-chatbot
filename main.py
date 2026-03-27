import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from fastapi import FastAPI, HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field

from sql_validation import SqlValidationError, validate_sql
from vanna_setup import (
    DB_PATH,
    check_openai_compatible_llm,
    create_agent,
    get_agent_memory_count,
    get_llm_settings,
    seed_agent_memory,
)


app = FastAPI(title="NL2SQL Clinic Assistant", version="1.0.0")


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)


class ChatResponse(BaseModel):
    message: str
    sql_query: Optional[str] = None
    columns: List[str] = []
    rows: List[List[Any]] = []
    row_count: int = 0
    chart: Optional[Dict[str, Any]] = None
    chart_type: Optional[str] = None


_agent = None
_cache: Dict[str, ChatResponse] = {}
_startup_seeded: bool = False
SQL_REGEX = re.compile(r"(SELECT[\s\S]+?;)", re.IGNORECASE)


def _ensure_agent():
    global _agent
    if _agent is None:
        _agent = create_agent()
    return _agent


def _db_connected() -> bool:
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("SELECT 1")
        conn.close()
        return True
    except Exception:
        return False


def _df_to_rows(df: pd.DataFrame, max_rows: int = 200) -> Tuple[List[str], List[List[Any]]]:
    if df is None:
        return [], []
    if len(df) > max_rows:
        df = df.head(max_rows)
    cols = [str(c) for c in df.columns.tolist()]
    rows = df.where(pd.notnull(df), None).values.tolist()
    return cols, rows


def _maybe_extract_sql(component: Any) -> Optional[str]:
    # Duck-typing across Vanna UiComponent variants.
    for attr in ("sql", "query", "code", "content", "text"):
        val = getattr(component, attr, None)
        if isinstance(val, str) and "select" in val.lower():
            s = val.strip().strip("`").strip()
            if s.lower().startswith(("select", "with")):
                return s

    # Tool-call shaped components often keep SQL in args.
    for attr in ("args", "tool_args", "arguments", "payload"):
        val = getattr(component, attr, None)
        if isinstance(val, dict):
            for key in ("sql", "query", "statement"):
                raw = val.get(key)
                if isinstance(raw, str) and raw.strip().lower().startswith(("select", "with")):
                    return raw.strip()

    # Pydantic models / dict-like components
    dump = None
    if hasattr(component, "model_dump"):
        try:
            dump = component.model_dump()
        except Exception:
            dump = None
    elif isinstance(component, dict):
        dump = component
    if isinstance(dump, dict):
        for key in ("sql", "query", "statement"):
            raw = dump.get(key)
            if isinstance(raw, str) and raw.strip().lower().startswith(("select", "with")):
                return raw.strip()
        for key in ("args", "tool_args", "arguments", "payload"):
            args = dump.get(key)
            if isinstance(args, dict):
                for inner_key in ("sql", "query", "statement"):
                    raw = args.get(inner_key)
                    if isinstance(raw, str) and raw.strip().lower().startswith(("select", "with")):
                        return raw.strip()

        # Last resort: search nested dict/list values for a SQL-looking string.
        stack: list[Any] = [dump]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, str):
                s = node.strip().strip("`").strip()
                if s.lower().startswith(("select ", "with ")):
                    return s
    return None


def _maybe_extract_df(component: Any) -> Optional[pd.DataFrame]:
    for attr in ("df", "dataframe", "data"):
        val = getattr(component, attr, None)
        if isinstance(val, pd.DataFrame):
            return val
    return None


def _maybe_extract_plotly(component: Any) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    # Plotly figures sometimes appear as dicts; sometimes as figure objects.
    for attr in ("plotly_json", "figure", "fig", "chart"):
        val = getattr(component, attr, None)
        if isinstance(val, dict) and ("data" in val or "layout" in val):
            return val, getattr(component, "chart_type", None) or getattr(component, "type", None)
    return None, None


def _extract_text(component: Any) -> Optional[str]:
    txt = getattr(component, "text", None) or getattr(component, "content", None)
    if isinstance(txt, str) and txt.strip():
        return txt.strip()

    dump = None
    if hasattr(component, "model_dump"):
        try:
            dump = component.model_dump()
        except Exception:
            dump = None
    elif isinstance(component, dict):
        dump = component

    if isinstance(dump, dict):
        for key in ("text", "content", "message", "value"):
            val = dump.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


def _extract_sql_with_regex(text: str) -> Optional[str]:
    if not text:
        return None
    m = SQL_REGEX.search(text)
    if m:
        return m.group(1).strip()
    # Fallback for responses that omit semicolon.
    lowered = text.lower()
    idx = lowered.find("select ")
    if idx >= 0:
        return text[idx:].strip()
    return None


def _generate_sql_with_ollama_fallback(question: str) -> Optional[str]:
    """
    Direct fallback when Vanna streaming components don't expose SQL.
    Uses Ollama's OpenAI-compatible endpoint.
    """
    llm = get_llm_settings()
    client = OpenAI(base_url=llm["base_url"], api_key=llm["api_key"])

    schema_hint = """
Tables:
patients(id, first_name, last_name, email, phone, date_of_birth, gender, city, registered_date)
doctors(id, name, specialization, department, phone)
appointments(id, patient_id, doctor_id, appointment_date, status, notes)
treatments(id, appointment_id, treatment_name, cost, duration_minutes)
invoices(id, patient_id, invoice_date, total_amount, paid_amount, status)
"""

    prompt = (
        "Return ONLY a valid SQLite SQL SELECT query with a trailing semicolon. "
        "No explanation, no markdown, no comments.\n\n"
        f"{schema_hint}\n"
        f"Question: {question}"
    )

    try:
        resp = client.chat.completions.create(
            model=llm["model"],
            messages=[
                {"role": "system", "content": "You generate SQL only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
    except Exception:
        return None

    text = ""
    try:
        text = (resp.choices[0].message.content or "").strip()
    except Exception:
        return None
    return _extract_sql_with_regex(text) or text


async def _collect_agent_components(question: str) -> List[Any]:
    agent = _ensure_agent()

    # Build a basic RequestContext if available; otherwise pass None.
    request_context = None
    try:
        from vanna.core.user import RequestContext

        request_context = RequestContext()
    except Exception:
        request_context = None

    # send_message streams UiComponents
    stream = agent.send_message(request_context=request_context, message=question)
    components: List[Any] = []
    async for c in stream:
        components.append(c)
    return components


@app.on_event("startup")
async def _startup() -> None:
    global _startup_seeded
    agent = _ensure_agent()
    try:
        await seed_agent_memory(agent)
        _startup_seeded = True
    except Exception:
        # Don’t block server start; /health will report seeding status.
        _startup_seeded = False


@app.get("/health")
def health():
    agent = _ensure_agent()
    llm = get_llm_settings()
    reachable, err, model_present = check_openai_compatible_llm(
        llm["base_url"], llm["api_key"], llm["model"]
    )
    return {
        "status": "ok",
        "database": "connected" if _db_connected() else "not_connected",
        "agent_memory_items": get_agent_memory_count(agent),
        "memory_seeded_on_startup": _startup_seeded,
        "ollama_or_llm_reachable": reachable,
        "llm_error": err,
        "model_loaded": model_present,
        "llm_base_url": llm["base_url"],
        "llm_model": llm["model"],
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    question = req.question.strip()
    if question in _cache:
        return _cache[question]

    # Ask the agent (stream), then post-process.
    try:
        components = await _collect_agent_components(question)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {e}")

    sql_query: Optional[str] = None
    df: Optional[pd.DataFrame] = None
    chart: Optional[Dict[str, Any]] = None
    chart_type: Optional[str] = None
    message_parts: List[str] = []

    for c in components:
        # Accumulate any textual content as the assistant message.
        txt = _extract_text(c)
        if isinstance(txt, str) and txt.strip():
            message_parts.append(txt.strip())

        if sql_query is None:
            sql_query = _maybe_extract_sql(c)
        if df is None:
            df = _maybe_extract_df(c)
        if chart is None:
            chart, chart_type = _maybe_extract_plotly(c)

    # Regex fallback: model may return explanatory text with SQL embedded.
    if sql_query is None and message_parts:
        joined = "\n".join(message_parts)
        sql_query = _extract_sql_with_regex(joined)

    # Hard fallback: ask Ollama directly for SQL-only output.
    if sql_query is None:
        sql_query = _generate_sql_with_ollama_fallback(question)

    # If we couldn't get a dataframe from components, execute ourselves (but still validate!).
    if sql_query:
        try:
            sql_query = validate_sql(sql_query)
        except SqlValidationError as e:
            return ChatResponse(
                message=f"I generated a query, but it was rejected by the SQL safety validator: {e}",
                sql_query=sql_query,
            )

        if df is None:
            try:
                conn = sqlite3.connect(DB_PATH)
                df = pd.read_sql_query(sql_query, conn)
                conn.close()
            except Exception as e:
                return ChatResponse(
                    message=f"I generated SQL but the database returned an error: {e}",
                    sql_query=sql_query,
                )

    if sql_query is None and df is None:
        return ChatResponse(
            message=(
                "I could not extract SQL from the model response. "
                "Please verify Ollama is running and the model is available, then retry."
            ),
            sql_query=None,
            columns=[],
            rows=[],
            row_count=0,
            chart=chart,
            chart_type=chart_type,
        )

    if df is not None and len(df) == 0:
        resp = ChatResponse(
            message="No data found for that question.",
            sql_query=sql_query,
            columns=list(df.columns) if df is not None else [],
            rows=[],
            row_count=0,
            chart=chart,
            chart_type=chart_type,
        )
        _cache[question] = resp
        return resp

    columns, rows = _df_to_rows(df) if df is not None else ([], [])
    msg = " ".join(message_parts).strip() or "Here are the results."

    resp = ChatResponse(
        message=msg,
        sql_query=sql_query,
        columns=columns,
        rows=rows,
        row_count=len(rows),
        chart=chart,
        chart_type=chart_type,
    )
    _cache[question] = resp
    return resp

