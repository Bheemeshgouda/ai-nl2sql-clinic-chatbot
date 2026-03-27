## AI-Powered Natural Language to SQL (NL2SQL) – Clinic Demo

This project is a working **Natural Language to SQL** chatbot over a small SQLite clinic database. It uses **Vanna AI 2.0** + **FastAPI** to generate SQL from English questions, validates the SQL for safety, executes it on SQLite, and returns results (and optionally charts).

### Tech stack

- **Python**: 3.10+
- **Backend**: FastAPI + Uvicorn
- **Database**: SQLite (`clinic.db`)
- **NL2SQL Agent**: Vanna AI 2.0.x
- **LLM provider (chosen)**: **Ollama (local)** via `OpenAILlmService` (OpenAI-compatible API)
- **Charts**: Plotly (when produced by the agent)

### Project files

- `setup_database.py`: creates schema + inserts realistic dummy data into `clinic.db`
- `vanna_setup.py`: initializes the Vanna 2.0 Agent (LLM + tools + DemoAgentMemory)
- `seed_memory.py`: pre-seeds agent memory with known good question–SQL pairs
- `sql_validation.py`: blocks non-SELECT and dangerous queries
- `main.py`: FastAPI app exposing `/chat` and `/health`
- `RESULTS.md`: record of the 20 required test questions

---

## Setup

### 1) Install Python

Install **Python 3.10+** and ensure it is on PATH.

You can verify with:

```bash
python --version
```

### 2) (Option A) Use Ollama (recommended: no API key)

1. Install Ollama: `https://ollama.com`
2. Pull a model:

```bash
ollama pull llama3
```

This project calls an OpenAI-compatible API at `http://localhost:11434/v1`.

Environment variables (optional):

- `OLLAMA_MODEL` (default: `llama3`)
- `OPENAI_BASE_URL` (default: `http://localhost:11434/v1`)
- `OPENAI_API_KEY` (default: `ollama`)

### 3) Install dependencies

```bash
pip install -r requirements.txt
```

### 4) Create the database + seed memory

```bash
python setup_database.py
python seed_memory.py
```

### 5) Start the API server

```bash
uvicorn main:app --port 8000
```

OpenAPI docs will be at `http://localhost:8000/docs`.

---

## API

### POST `/chat`

Request body:

```json
{ "question": "Top 5 patients by spending" }
```

Response body (example shape):

```json
{
  "message": "Here are the results.",
  "sql_query": "SELECT ...",
  "columns": ["id", "first_name", "last_name", "total_spending"],
  "rows": [[1, "John", "Smith", 4500.0]],
  "row_count": 1,
  "chart": null,
  "chart_type": null
}
```

Notes:
- SQL is always validated to be **SELECT/CTE-only** before execution.
- If the agent stream doesn’t include a table payload, the backend executes the validated SQL itself.
- Results are capped to 200 rows in the JSON response.

### GET `/health`

Returns:

```json
{ "status": "ok", "database": "connected", "agent_memory_items": 15 }
```

---

## Architecture (brief)

1. **User question** → `POST /chat`
2. **Vanna Agent** generates tool calls / SQL
3. **SQL validation** (`sql_validation.py`) blocks non-SELECT + dangerous queries
4. **SQLite execution** (built-in `SqliteRunner` in the agent; backend falls back to `sqlite3` if needed)
5. **Response**: message + SQL + tabular results + optional Plotly chart JSON

---

## Running the assignment’s command

```bash
pip install -r requirements.txt && python setup_database.py && python seed_memory.py && uvicorn main:app --port 8000
```

