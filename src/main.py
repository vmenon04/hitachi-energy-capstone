import os
import uuid

from pathlib import Path
from dotenv import load_dotenv

from utils.logging_utils import setup_logger, log_section, log_subsection
from utils.data_utils import download_csv
from agents.agents import generate_insights, generate_chart_plan

from datafetching.refresh_extraction import sharepoint_to_blob
from notifications.email_utils import send_insights_email
from visualizations.html_report import build_and_upload_chart_htmls

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
        logger.info("Loaded %d CSV files from Blob Storage", len(dfs))

        log_subsection("STEP 3: GENERATE AI INSIGHTS")
        insights_result = generate_insights(dfs)
        insights_text = insights_result["messages"][-1].content if insights_result else ""

        if insights_text:
            log_subsection("STEP 4: GENERATE AI CHART PLAN")
            logger.info("Generating AI chart plan")
            chart_plan = generate_chart_plan(dfs, insights_text)

            log_subsection("STEP 5: BUILD AND UPLOAD HTML CHARTS")
            logger.info("Generating interactive HTML charts and uploading to blob storage")
            chart_paths, chart_images = build_and_upload_chart_htmls(
                dfs=dfs,
                chart_plan=chart_plan,
                connection_string=STORAGE_CONNECTION_STRING,
                container_name=REPORTS_CONTAINER_NAME,
            )
            logger.info("Generated %d HTML charts", len(chart_paths))

            log_subsection("STEP 6: SEND EMAIL")
            logger.info("Sending insights email with chart images")
            send_insights_email(
                insights_text,
                csv_name="Combined Blob Storage Datasets",
                chart_images=chart_images,
            )

            log_section("JOB COMPLETED SUCCESSFULLY")
        else:
            logger.warning("No insights generated; skipping email send")

    except Exception:
        logger.exception("Unhandled exception in job entrypoint")
        raise


if __name__ == "__main__":
    main()