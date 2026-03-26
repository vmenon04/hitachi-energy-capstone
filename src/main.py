import os
import io
import logging
import sys
import uuid
import json
import time

from pathlib import Path
import pandas as pd
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient
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

from datafetching.refresh_extraction import sharepoint_to_blob
from notifications.email_utils import send_insights_email
from systemprompts.prompts import (
    INSIGHTS_SYSTEM,
    INSIGHTS_HUMAN,
    CHART_PLANNER_SYSTEM,
    CHART_PLANNER_HUMAN_TEMPLATE,
)
from tools.tools import get_tools
from visualizations.html_report import build_and_upload_chart_htmls

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

STORAGE_CONNECTION_STRING = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
STORAGE_CONTAINER_NAME = os.environ["AZURE_STORAGE_CONTAINER_NAME"]
REPORTS_CONTAINER_NAME = os.environ.get("AZURE_REPORTS_CONTAINER_NAME", "bi-reports")
AI_ENDPOINT = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
AI_API_KEY = os.environ["AZURE_AI_PROJECT_API_KEY"]

MODEL = "gpt-5.4-mini"

# module-level values that give each log line context about which job run produced it
JOB_NAME = os.getenv("CONTAINER_APP_JOB_NAME", "hitachi-job")
EXECUTION_ID = os.getenv("JOB_EXECUTION_ID", str(uuid.uuid4()))

# Global variable to store the current dataframe for tool access
current_dfs = {}


class _JsonFormatter(logging.Formatter):
    """
    Emits one JSON object per log record on a single line.

    Each record has:
      timestamp, level, job, execution_id, message

    Exceptions are serialised into an 'exception' field as a single escaped
    string rather than being printed as multi-line text.  This means every
    log entry, including full stack traces, lands in exactly one
    Log Analytics row and is trivially queryable with:

        ContainerAppConsoleLogs_CL
        | where TimeGenerated > ago(1h)
        | extend rec = parse_json(Log_s)
        | where rec.level == "ERROR"
        | project TimeGenerated, rec.execution_id, rec.message, rec.exception
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "job": JOB_NAME,
            "execution_id": EXECUTION_ID,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("hitachi_pipeline")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)

    return logger


logger = setup_logger()


def log_section(title: str) -> None:
    logger.info("=== %s ===", title)


def log_subsection(title: str) -> None:
    logger.info("--- %s ---", title)


def log_iteration(iteration: int) -> None:
    logger.info("--- Iteration %d ---", iteration)


def download_csv() -> dict[str, pd.DataFrame]:
    logger.info(
        "Downloading CSV files from Blob Storage: container=%s",
        STORAGE_CONTAINER_NAME,
    )

    client = BlobServiceClient.from_connection_string(STORAGE_CONNECTION_STRING)
    container = client.get_container_client(container=STORAGE_CONTAINER_NAME)

    dataframes = {}

    for blob in container.list_blobs():
        if blob.name.lower().endswith(".csv"):
            logger.info("Downloading %s from %s...", blob.name, STORAGE_CONTAINER_NAME)
            blob_client = container.get_blob_client(blob.name)
            data = blob_client.download_blob().readall()
            df = pd.read_csv(io.BytesIO(data))
            dataframes[blob.name] = df

    return dataframes

# Retry decorator for Azure OpenAI 429 rate-limit errors.
# Waits 60–300 s between attempts (exponential backoff) for up to 5 tries.
_llm_retry = retry(
    retry=retry_if_exception_type(RateLimitError),
    wait=wait_exponential(multiplier=1, min=60, max=300),
    stop=stop_after_attempt(5),
    before_sleep=before_sleep_log(logging.getLogger("hitachi_pipeline"), logging.WARNING),
    reraise=True,
)


def generate_insights(data: dict[str, pd.DataFrame]):
    global current_dfs
    current_dfs = data

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
    result = _llm_retry(lambda: agent.invoke({"messages": messages}))
    return result

def build_dataset_metadata(dfs: dict[str, pd.DataFrame]) -> str:
    lines = []

    for dataset_name, df in dfs.items():
        cols = []
        for col in df.columns:
            dtype = str(df[col].dtype)
            cols.append(f"{col} ({dtype})")

        lines.append(f"Dataset: {dataset_name}")
        lines.append(f"Rows: {len(df)}, Columns: {len(df.columns)}")
        lines.append("Columns:")
        for c in cols:
            lines.append(f"  - {c}")
        lines.append("")

    return "\n".join(lines)


def generate_chart_plan(dfs: dict[str, pd.DataFrame], insights_text: str) -> dict:
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

    response = _llm_retry(lambda: llm.invoke(messages))
    raw = response.content.strip()

    logger.info("Raw chart planner output received")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned)


def main():
    log_section("HITACHI AI PROJECT TRACKING JOB STARTED")

    try:
        log_subsection("STEP 1: SYNC FROM SHAREPOINT / ONEDRIVE")
        sharepoint_client_id = os.getenv("SHAREPOINT_CLIENT_ID")
        if sharepoint_client_id:
            drive_id = os.environ["SHAREPOINT_DRIVE_ID"]
            folder_id = os.environ.get("SHAREPOINT_FOLDER_ID", "root")
            logger.info("SharePoint ingestion enabled; syncing drive=%s", drive_id)
            sharepoint_to_blob(drive_id, folder_id)
            logger.info("SharePoint sync complete")
        else:
            logger.info("SHAREPOINT_CLIENT_ID not set; skipping SharePoint sync")

        log_subsection("STEP 2: DOWNLOAD CSV FILES")
        dfs = download_csv()
        logger.info("Loaded %d CSV files from Blob Storage", len(dfs))

        log_subsection("STEP 3: GENERATE AI INSIGHTS")
        insights = generate_insights(dfs)

        if insights:
            log_subsection("STEP 4: GENERATE AI CHART PLAN")
            logger.info("Generating AI chart plan")
            chart_plan = generate_chart_plan(dfs, insights)

            log_subsection("STEP 5: BUILD AND UPLOAD HTML CHARTS")
            logger.info("Generating interactive HTML charts and uploading to blob storage")
            chart_paths = build_and_upload_chart_htmls(
                dfs=dfs,
                chart_plan=chart_plan,
                connection_string=STORAGE_CONNECTION_STRING,
                container_name=REPORTS_CONTAINER_NAME,
            )
            logger.info("Generated %d HTML charts", len(chart_paths))

            log_subsection("STEP 6: SEND EMAIL")
            logger.info("Sending insights email with HTML chart attachments")
            send_insights_email(
                insights,
                csv_name="Combined Blob Storage Datasets",
                attachment_paths=chart_paths,
            )

            log_section("JOB COMPLETED SUCCESSFULLY")
        else:
            logger.warning("No insights generated; skipping email send")

    except Exception:
        logger.exception("Unhandled exception in job entrypoint")
        raise


if __name__ == "__main__":
    main()