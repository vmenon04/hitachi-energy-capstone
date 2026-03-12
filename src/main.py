import os
import base64
import pandas as pd
import io
import time
import logging
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from azure.identity import DefaultAzureCredential
from langchain_azure_ai.agents import AgentServiceFactory
from langchain_azure_ai.utils.agents import pretty_print
from langchain_azure_ai.agents.prebuilt.tools import CodeInterpreterTool
from azure.storage.blob import BlobServiceClient
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from tools.tools import get_tools
from systemprompts.prompts import INSIGHTS_SYSTEM, INSIGHTS_HUMAN
from typing import Optional

load_dotenv()

logging.getLogger("langchain_azure_ai").setLevel(logging.DEBUG)

# Global variable to store the current dataframe for tool access
current_dfs: dict[str, pd.DataFrame] = {}

STORAGE_CONNECTION_STRING = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
STORAGE_CONTAINER_NAME = os.environ["AZURE_STORAGE_CONTAINER_NAME"]
AI_ENDPOINT = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
AI_API_KEY = os.environ["AZURE_AI_PROJECT_API_KEY"]

def download_csv() -> pd.DataFrame:
    client = BlobServiceClient.from_connection_string(STORAGE_CONNECTION_STRING)
    container = client.get_container_client(container=STORAGE_CONTAINER_NAME)

    dataFrames = {}

    for blob in container.list_blobs():
        if blob.name.lower().endswith(".csv"):
            print(f"Downloading {blob.name} from {STORAGE_CONTAINER_NAME}...")
            blob_client = container.get_blob_client(blob.name)
            data = blob_client.download_blob().readall()
            df = pd.read_csv(io.BytesIO(data))
            dataFrames[blob.name] = df

    return dataFrames


def generate_insights(df: pd.DataFrame) -> Optional[str]:
    global current_dfs
    current_dfs = df
    
    factory = AgentServiceFactory(
        project_endpoint=AI_ENDPOINT,
        credential=DefaultAzureCredential(),
    )

    # tools = get_tools(current_dfs) + [CodeInterpreterTool()]
    tools = get_tools(current_dfs)

    agent = factory.create_prompt_agent(
        name="code-interpreter-agent",
        model="gpt-4o",
        instructions=INSIGHTS_SYSTEM,
        tools=tools,
    )

    def run_agent_with_retry(messages, max_retries=3):
        """Run the agent with retry logic for transient failures."""
        for attempt in range(max_retries):
            try:
                logging.debug(f"Attempting to invoke agent (attempt {attempt + 1}/{max_retries})")
                response = agent.invoke({"messages": messages})
                return response
            except Exception as e:
                if "No tool output found" in str(e):
                    if attempt < max_retries - 1:
                        logging.warning(f"Tool output missing, retrying after 2s (attempt {attempt + 1}/{max_retries})")
                        time.sleep(2)
                        continue
                raise

    messages = [HumanMessage(content=INSIGHTS_HUMAN)]
    response = run_agent_with_retry(messages=messages, max_retries=10)
    pretty_print(response)

def main():
    dfs = download_csv()
    print(f"Loaded {len(dfs)} CSV files from Blob Storage")
    generate_insights(dfs)


if __name__ == "__main__":
    main()