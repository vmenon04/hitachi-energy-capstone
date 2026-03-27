import os
import logging
import json

from pathlib import Path
import pandas as pd
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.agents import create_agent
from openai import RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from utils.data_utils import build_dataset_metadata

from systemprompts.prompts import (
    INSIGHTS_SYSTEM,
    INSIGHTS_HUMAN,
    CHART_PLANNER_SYSTEM,
    CHART_PLANNER_HUMAN_TEMPLATE,
)
from tools.tools import get_tools

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

AI_ENDPOINT = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
AI_API_KEY = os.environ["AZURE_AI_PROJECT_API_KEY"]

MODEL = "gpt-5.4-mini"

def _wait_retry_after_or_exponential(retry_state):
    """Use the Retry-After header value from the 429 response if present;
    otherwise fall back to exponential backoff (60-300 s)."""
    exc = retry_state.outcome.exception()
    if exc is not None:
        response = getattr(exc, "response", None)
        if response is not None:
            header = response.headers.get("retry-after") or response.headers.get("Retry-After")
            if header:
                try:
                    return float(header)
                except (ValueError, TypeError):
                    pass
    return wait_exponential(multiplier=1, min=60, max=300)(retry_state)


# Retry decorator for Azure OpenAI 429 rate-limit errors.
# Respects the Retry-After header; falls back to exponential backoff (60–300 s).
_llm_retry = retry(
    retry=retry_if_exception_type(RateLimitError),
    wait=_wait_retry_after_or_exponential,
    stop=stop_after_attempt(5),
    before_sleep=before_sleep_log(logging.getLogger("hitachi_pipeline"), logging.WARNING),
    reraise=True,
)

def generate_insights(data: dict[str, pd.DataFrame]):
    global current_dfs
    current_dfs = data

    logger = logging.getLogger("hitachi_pipeline")

    logger.info("Initializing Azure OpenAI client: model=%s", MODEL)

    llm = AzureChatOpenAI(
        azure_endpoint=AI_ENDPOINT,
        api_key=AI_API_KEY,
        api_version="2024-12-01-preview",
        deployment_name=MODEL,
        temperature=0.5
    )

    tools = get_tools(current_dfs)

    logger.info("Creating agent")
    agent = create_agent(llm, 
                         tools=tools, 
                         system_prompt=INSIGHTS_SYSTEM, 
                         name="basic-agent"
    )
    messages = [HumanMessage(content=INSIGHTS_HUMAN)]

    logger.info("Starting insight generation with tool calls")
    result = _llm_retry(lambda: agent.invoke({"messages": messages}))()
    return result


def generate_chart_plan(dfs: dict[str, pd.DataFrame], insights_text: str) -> dict:
    logger = logging.getLogger("hitachi_pipeline")

    llm = AzureChatOpenAI(
        azure_endpoint=AI_ENDPOINT,
        api_key=AI_API_KEY,
        api_version="2024-12-01-preview",
        deployment_name=MODEL,
        temperature=0.3
    )

    dataset_metadata = build_dataset_metadata(dfs)
    human_prompt = CHART_PLANNER_HUMAN_TEMPLATE.format(
        insights=insights_text,
        dataset_metadata=dataset_metadata,
    )

    messages = [
        SystemMessage(content=CHART_PLANNER_SYSTEM),
        HumanMessage(content=human_prompt),
    ]

    response = _llm_retry(lambda: llm.invoke(messages))()
    raw = response.content.strip()

    logger.info("Raw chart planner output received")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned)