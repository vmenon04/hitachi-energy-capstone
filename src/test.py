import os
import base64
import pandas as pd
import io
import time
import logging
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from azure.identity import DefaultAzureCredential
from langchain_azure_ai.agents import AgentServiceFactory
from langchain_azure_ai.utils.agents import pretty_print
from langchain_azure_ai.agents.prebuilt.tools import CodeInterpreterTool
from azure.storage.blob import BlobServiceClient
from langchain_core.messages import HumanMessage
from tools.tools import get_tools
from systemprompts.prompts import INSIGHTS_SYSTEM, INSIGHTS_HUMAN
from typing import Optional
from langchain_openai import AzureChatOpenAI
from langchain.agents import create_agent

load_dotenv()

logging.getLogger("langchain_azure_ai").setLevel(logging.DEBUG)

# Global variable to store the current dataframe for tool access
current_dfs: dict[str, pd.DataFrame] = {}

STORAGE_CONNECTION_STRING = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
STORAGE_CONTAINER_NAME = os.environ["AZURE_STORAGE_CONTAINER_NAME"]
AI_ENDPOINT = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
AI_API_KEY = os.environ["AZURE_AI_PROJECT_API_KEY"]

MODEL = "gpt-5.4-mini"

def download_csv() -> dict[str, bytes]:
    client = BlobServiceClient.from_connection_string(STORAGE_CONNECTION_STRING)
    container = client.get_container_client(container=STORAGE_CONTAINER_NAME)

    raw_files = {}

    for blob in container.list_blobs():
        if blob.name.lower().endswith(".csv"):
            print(f"Downloading {blob.name} from {STORAGE_CONTAINER_NAME}...")
            blob_client = container.get_blob_client(blob.name)
            data = blob_client.download_blob().readall()
            raw_files[blob.name] = data

    return raw_files

def generate_insights(raw_files: dict[str, pd.DataFrame]):
    global current_dfs
    current_dfs = {name: pd.read_csv(io.BytesIO(data)) for name, data in raw_files.items()}

    llm = AzureChatOpenAI(
        azure_endpoint=AI_ENDPOINT,
        api_key=AI_API_KEY,
        api_version="2024-12-01-preview",
        deployment_name=MODEL,
        temperature=0.5
    )

    tools = get_tools(current_dfs)
    agent = create_agent(llm, tools=tools, system_prompt=INSIGHTS_SYSTEM, name="basic-agent")
    messages = [HumanMessage(content=INSIGHTS_HUMAN)]
    result = agent.invoke({"messages": messages})
    return result


def main():
    dfs = download_csv()
    print(f"Loaded {len(dfs)} CSV files from Blob Storage")
    response = generate_insights(dfs)
    pretty_print(response)


if __name__ == "__main__":
    main()