import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

from vanna import Agent, AgentConfig
from vanna.core.registry import ToolRegistry
from vanna.core.user import RequestContext, User, UserResolver
from vanna.integrations.local.agent_memory import DemoAgentMemory
from vanna.integrations.openai import OpenAILlmService
from vanna.integrations.sqlite import SqliteRunner
from vanna.tools import RunSqlTool, VisualizeDataTool
from vanna.tools.agent_memory import SaveQuestionToolArgsTool, SearchSavedCorrectToolUsesTool


DB_PATH = Path(__file__).with_name("clinic.db")
SQL_ONLY_INSTRUCTION = (
    "You are an NL2SQL generator for SQLite. "
    "Return ONLY a valid SQL SELECT query. "
    "Do not include explanations, comments, or markdown. "
    "Return raw SQL text only."
)


class DefaultUserResolver(UserResolver):
    async def resolve_user(self, request_context: RequestContext) -> User:
        # Single-user assignment environment: treat everyone as the same user.
        return User(id="default_user", email="default_user@example.com", group_memberships=["admin", "user"])


def get_llm_settings() -> dict[str, str]:
    return {
        "base_url": "http://localhost:11434/v1",
        "api_key": "ollama",
        "model": "llama3",
    }


def _create_ollama_llm(model: str, api_key: str, base_url: str) -> OpenAILlmService:
    # Different Vanna versions expose slightly different kwargs.
    # Try strict instruction fields first; fall back gracefully.
    candidate_kwargs = [
        {
            "model": model,
            "api_key": api_key,
            "base_url": base_url,
            "system_prompt": SQL_ONLY_INSTRUCTION,
        },
        {
            "model": model,
            "api_key": api_key,
            "base_url": base_url,
            "instructions": SQL_ONLY_INSTRUCTION,
        },
        {
            "model": model,
            "api_key": api_key,
            "base_url": base_url,
        },
    ]
    for kwargs in candidate_kwargs:
        try:
            return OpenAILlmService(**kwargs)
        except TypeError:
            continue
    # Final direct attempt (surfaces any non-TypeError issues).
    return OpenAILlmService(model=model, api_key=api_key, base_url=base_url)


def _create_agent_config() -> AgentConfig:
    # Different AgentConfig versions may support different instruction fields.
    candidate_kwargs = [
        {"system_prompt": SQL_ONLY_INSTRUCTION},
        {"instructions": SQL_ONLY_INSTRUCTION},
        {"developer_prompt": SQL_ONLY_INSTRUCTION},
    ]
    for kwargs in candidate_kwargs:
        try:
            return AgentConfig(**kwargs)
        except TypeError:
            continue
    return AgentConfig()


def check_openai_compatible_llm(base_url: str, api_key: str, model: str) -> Tuple[bool, Optional[str], bool]:
    """
    Returns:
      - reachable: can we call GET {base_url}/models ?
      - error: error string if not reachable
      - model_present: whether `model` appears in the model list (best-effort)
    """
    url = base_url.rstrip("/") + "/models"
    req = urllib.request.Request(url, method="GET")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        return False, str(e), False
    except Exception as e:
        return False, str(e), False

    model_present = bool(model) and (model.lower() in raw.lower())
    return True, None, model_present


def create_agent() -> Agent:
    """
    Uses an OpenAI-compatible LLM endpoint. For this assignment we default to Ollama:
    - base_url: http://localhost:11434/v1
    - api_key: ollama (dummy)
    - model: llama3 (customizable via OLLAMA_MODEL)
    """
    settings = get_llm_settings()
    base_url = settings["base_url"]
    api_key = settings["api_key"]
    model = settings["model"]

    llm = _create_ollama_llm(model=model, api_key=api_key, base_url=base_url)

    tools = ToolRegistry()
    tools.register_local_tool(
        RunSqlTool(
            sql_runner=SqliteRunner(database_path=str(DB_PATH)),
            custom_tool_description=(
                "Execute a SQLite SELECT query only. "
                "Arguments must contain raw SQL in args.sql. "
                "Do not provide explanations."
            ),
        ),
        access_groups=["admin", "user"],
    )
    tools.register_local_tool(VisualizeDataTool(), access_groups=["admin", "user"])
    tools.register_local_tool(SaveQuestionToolArgsTool(), access_groups=["admin"])
    tools.register_local_tool(SearchSavedCorrectToolUsesTool(), access_groups=["admin", "user"])

    agent_memory = DemoAgentMemory(max_items=1000)

    return Agent(
        llm_service=llm,
        tool_registry=tools,
        user_resolver=DefaultUserResolver(),
        agent_memory=agent_memory,
        config=_create_agent_config(),
    )


async def seed_agent_memory(agent: Agent) -> int:
    """
    Seeds DemoAgentMemory inside the *running server process*.
    This is required because DemoAgentMemory is in-memory (not shared across processes).
    """
    from seed_memory import seed_agent_memory as _seed

    return await _seed(agent)


def get_agent_memory_count(agent: Agent) -> int:
    """
    Best-effort helper for /health.
    DemoAgentMemory API may vary slightly; we try common attributes.
    """
    mem = getattr(agent, "agent_memory", None)
    for attr in ("items", "_items", "memories", "_memories"):
        val = getattr(mem, attr, None)
        if isinstance(val, list):
            return len(val)
    return 0

