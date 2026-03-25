import os
import io
import logging
import sys
import uuid
import json

from pathlib import Path
from typing import Optional
import pandas as pd
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from notifications.email_utils import send_insights_email
from systemprompts.prompts import (
    INSIGHTS_SYSTEM,
    INSIGHTS_HUMAN,
    CHART_PLANNER_SYSTEM,
    CHART_PLANNER_HUMAN_TEMPLATE,
)
from tools.tools import get_tools
from visualizations.pdf_report import (
    build_visualization_pdf,
    verify_plotly_export_environment,
)

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

STORAGE_CONNECTION_STRING = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
STORAGE_CONTAINER_NAME = os.environ["AZURE_STORAGE_CONTAINER_NAME"]
AI_ENDPOINT = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
AI_API_KEY = os.environ["AZURE_AI_PROJECT_API_KEY"]

MODEL = "gpt-5.4-mini"

# module-level values that give each log line context about which job run produced it
JOB_NAME = os.getenv("CONTAINER_APP_JOB_NAME", "hitachi-job")
EXECUTION_ID = os.getenv("JOB_EXECUTION_ID", str(uuid.uuid4()))

# Global variable to store the current dataframe for tool access
current_dfs = {}


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.job_name = JOB_NAME
        record.execution_id = EXECUTION_ID
        return True


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("hitachi_pipeline")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt=(
                "%(asctime)s %(levelname)s %(name)s "
                "[job=%(job_name)s execution_id=%(execution_id)s] %(message)s"
            )
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.addFilter(ContextFilter())

    return logger


logger = setup_logger()


def log_section(title: str) -> None:
    line = "=" * 80
    logger.info("\n%s\n%s\n%s", line, title, line)


def log_subsection(title: str) -> None:
    line = "-" * 60
    logger.info("\n%s\n%s\n%s", line, title, line)


def log_iteration(iteration: int) -> None:
    line = "-" * 25
    logger.info("\n%s Iteration %d %s", line, iteration, line)


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


def generate_insights(df: dict[str, pd.DataFrame]) -> Optional[str]:
    global current_dfs
    current_dfs = df

    logger.info("Initializing Azure OpenAI client: model=%s", MODEL)

    llm = AzureChatOpenAI(
        azure_endpoint=AI_ENDPOINT,
        api_key=AI_API_KEY,
        api_version="2024-12-01-preview",
        deployment_name=MODEL,
        temperature=0.5
    )

    tools = get_tools(current_dfs)
    llm_with_tools = llm.bind_tools(tools)

    try:
        messages = [
            SystemMessage(content=INSIGHTS_SYSTEM),
            HumanMessage(content=INSIGHTS_HUMAN),
        ]

        logger.info("Starting insight generation with tool calls")

        max_iterations = 10
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            log_iteration(iteration)
            logger.info("LLM iteration started")

            response = llm_with_tools.invoke(messages)
            messages.append(response)

            logger.info(
                "LLM response received: iteration=%d finish_reason=%s has_tool_calls=%s content_length=%d",
                iteration,
                response.response_metadata.get("finish_reason", "unknown"),
                bool(response.tool_calls),
                len(response.content) if response.content else 0,
            )

            if response.tool_calls:
                logger.info(
                    "Executing tool calls: iteration=%d count=%d",
                    iteration,
                    len(response.tool_calls),
                )

                available_tools = {
                    "get_files": tools[0],
                    "get_data_summary": tools[1],
                    "calculate_column_statistics": tools[2],
                    "get_column_info": tools[3]
                }

                tool_executed = False
                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]

                    logger.info(
                        "Calling tool: name=%s args=%s",
                        tool_name,
                        tool_args,
                    )
                    try:
                        tool_function = available_tools[tool_name]
                        tool_result = tool_function.invoke(tool_args)
                        tool_executed = True

                        logger.info(
                            "Tool call completed successfully: name=%s result_length=%d",
                            tool_name,
                            len(str(tool_result)),
                        )

                        messages.append(
                            ToolMessage(
                                content=str(tool_result),
                                tool_call_id=tool_call["id"]
                            )
                        )
                    except Exception as tool_error:
                        logger.exception("Tool execution error: %s", tool_error)
                        messages.append(
                            ToolMessage(
                                content=f"Error executing tool: {str(tool_error)}",
                                tool_call_id=tool_call["id"]
                            )
                        )

                if not tool_executed:
                    logger.warning(
                        "No tool calls executed successfully; breaking loop: iteration=%d",
                        iteration
                    )
                    break
            else:
                logger.info("Model completed analysis without requesting further tool calls")
                break

        final_insights: Optional[str] = None
        for msg in reversed(messages):
            if hasattr(msg, "content") and msg.content and msg.__class__.__name__ == "AIMessage":
                final_insights = msg.content
                break

        if final_insights:
            logger.info("Insight generation completed successfully")
        else:
            logger.warning("No final AI text response was generated")

        return final_insights

    except Exception:
        logger.exception("Unhandled exception during insight generation")
        return None


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

    response = llm.invoke(messages)
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
        log_subsection("STEP 1: VERIFY PLOTLY / KALEIDO ENVIRONMENT")
        logger.info("Checking Plotly/Kaleido export environment")
        verify_plotly_export_environment()

        log_subsection("STEP 2: DOWNLOAD CSV FILES")
        dfs = download_csv()
        logger.info("Loaded %d CSV files from Blob Storage", len(dfs))

        log_subsection("STEP 3: GENERATE AI INSIGHTS")
        insights = generate_insights(dfs)

        if insights:
            log_subsection("STEP 4: GENERATE AI CHART PLAN")
            logger.info("Generating AI chart plan")
            chart_plan = generate_chart_plan(dfs, insights)

            log_subsection("STEP 5: BUILD PDF REPORT")
            logger.info("Generating PDF report")
            pdf_path = build_visualization_pdf(
                dfs=dfs,
                insights_text=insights,
                chart_plan=chart_plan,
                output_pdf_path=str(BASE_DIR / "reports" / "project_tracking_visualizations.pdf"),
            )

            logger.info("Generated PDF report at: %s", pdf_path)

            log_subsection("STEP 6: SEND EMAIL")
            logger.info("Sending insights email with PDF attachment")
            send_insights_email(
                insights,
                csv_name="Combined Blob Storage Datasets",
                attachment_paths=[pdf_path],
            )

            log_section("JOB COMPLETED SUCCESSFULLY")
        else:
            logger.warning("No insights generated; skipping email send")

    except Exception:
        logger.exception("Unhandled exception in job entrypoint")
        raise


if __name__ == "__main__":
    main()