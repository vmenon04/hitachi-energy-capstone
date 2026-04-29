import os
import uuid

from pathlib import Path
from dotenv import load_dotenv

from utils.logging_utils import setup_logger, log_section, log_subsection
from utils.data_utils import download_csv, NoDataInputError
from agents.agents import generate_insights, generate_chart_plan

from datafetching.refresh_extraction import sharepoint_to_blob
from notifications.email_utils import send_insights_email
from visualizations.html_report import build_and_upload_chart_htmls
from systemprompts.prompts import PERSONAS

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

STORAGE_CONNECTION_STRING = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
STORAGE_CONTAINER_NAME = os.environ["AZURE_STORAGE_CONTAINER_NAME"]
REPORTS_CONTAINER_NAME = os.environ.get("AZURE_REPORTS_CONTAINER_NAME", "bi-reports")

# module-level values that give each log line context about which job run produced it
JOB_NAME = os.getenv("CONTAINER_APP_JOB_NAME", "hitachi-job")
EXECUTION_ID = os.getenv("JOB_EXECUTION_ID", str(uuid.uuid4()))

# Global variable to store the current dataframe for tool access
current_dfs = {}

logger = setup_logger(JOB_NAME, EXECUTION_ID)

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
        dfs = download_csv(STORAGE_CONNECTION_STRING, STORAGE_CONTAINER_NAME)
        if len(dfs) == 0:
            logger.error(f"No CSV files found in Blob Storage container={STORAGE_CONTAINER_NAME}")
            raise NoDataInputError("No CSV files to process")
        logger.info("Loaded %d CSV files from Blob Storage", len(dfs))

        log_subsection("STEP 3-6: GENERATE PERSONA REPORTS")
        logger.info("Generating tailored reports for %d personas", len(PERSONAS))

        for persona_key, persona_config in PERSONAS.items():
            logger.info(f"Starting persona report generation: {persona_config.name} ({persona_key})")

            recipients = [recipient.strip() for recipient in persona_config.email_recipients if recipient.strip()]
            if not recipients:
                logger.warning("No email recipients configured for persona=%s; skipping send", persona_key)
                continue

            insights_result = generate_insights(
                dfs,
                system_prompt=persona_config.insights_system_prompt,
            )
            insights_text = insights_result["messages"][-1].content if insights_result else ""
            logger.info("Insights length for persona=%s: %d chars", persona_key, len(insights_text))

            if not insights_text:
                logger.warning("No insights generated for persona=%s; skipping", persona_key)
                continue

            logger.info("Generating chart plan for persona=%s", persona_key)
            chart_plan = generate_chart_plan(
                dfs,
                insights_text,
                system_prompt=persona_config.chart_planner_prompt,
            )
            num_datasets = len(chart_plan.get("datasets", [])) if chart_plan else 0
            num_charts = sum(len(d.get("charts", [])) for d in chart_plan.get("datasets", [])) if chart_plan else 0

            logger.info("Chart plan for persona=%s: %d datasets, %d charts", persona_key, num_datasets, num_charts,)

            logger.info("Building and uploading HTML charts for persona=%s", persona_key)
            chart_paths, chart_images = build_and_upload_chart_htmls(
                dfs=dfs,
                chart_plan=chart_plan,
                connection_string=STORAGE_CONNECTION_STRING,
                container_name=REPORTS_CONTAINER_NAME,
                persona=persona_key,
            )
            logger.info("Chart images for persona=%s: %d",persona_key,len(chart_images),)
            logger.info(
                "Generated %d HTML charts for persona=%s",
                len(chart_paths),
                persona_key,
            )

            logger.info("Sending tailored email for persona=%s", persona_key)
            send_insights_email(
                insights_text,
                csv_name="Combined Blob Storage Datasets",
                chart_images=chart_images,
                subject=f"{persona_config.name} Insights Report",
                recipients=recipients,
                persona=persona_key,
            )

        log_section("JOB COMPLETED SUCCESSFULLY")

    except Exception:
        logger.exception("Unhandled exception in job entrypoint")
        raise


if __name__ == "__main__":
    main()