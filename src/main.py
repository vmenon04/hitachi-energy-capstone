import os
import io
from typing import Optional
import pandas as pd
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient
from langchain_openai import AzureChatOpenAI
from langchain.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from notifications.email_utils import send_insights_email
from systemprompts.prompts import INSIGHTS_SYSTEM, INSIGHTS_HUMAN

load_dotenv()

STORAGE_CONNECTION_STRING = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
STORAGE_CONTAINER_NAME = os.environ["AZURE_STORAGE_CONTAINER_NAME"]
AI_ENDPOINT = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
AI_API_KEY = os.environ["AZURE_AI_PROJECT_API_KEY"]

CSV_BLOB_NAME = "sample2.csv"
MODEL = "gpt-4o"

# Global variable to store the current dataframe for tool access
current_df = None

def download_csv() -> pd.DataFrame:
    client = BlobServiceClient.from_connection_string(STORAGE_CONNECTION_STRING)
    blob_client = client.get_blob_client(container=STORAGE_CONTAINER_NAME, blob=CSV_BLOB_NAME)
    print(f"Downloading {CSV_BLOB_NAME} from {STORAGE_CONTAINER_NAME}...")
    data = blob_client.download_blob().readall()
    df = pd.read_csv(io.BytesIO(data))
    df.columns = df.columns.str.strip()
    return df


# Define tools for CSV analysis
@tool
def get_data_summary() -> str:
    """Get a summary of the CSV data including shape, columns, and first few rows.
    
    Returns:
        A string summary of the CSV file
    """
    try:
        summary = f"CSV Data Summary:\n"
        summary += f"Shape: {current_df.shape[0]} rows, {current_df.shape[1]} columns\n"
        summary += f"Columns: {', '.join(current_df.columns.tolist())}\n"
        summary += f"\nFirst 5 rows:\n{current_df.head().to_string()}"
        return summary
    except Exception as e:
        return f"Error getting data summary: {str(e)}"


@tool
def calculate_column_statistics(column_name: str) -> str:
    """Calculate basic statistics for a numeric column in the CSV file.
    
    Args:
        column_name: Name of the column to analyze
        
    Returns:
        Statistical summary of the column
    """
    try:
        if column_name not in current_df.columns:
            return f"Column '{column_name}' not found. Available columns: {', '.join(current_df.columns.tolist())}"
        
        stats = current_df[column_name].describe()
        return f"Statistics for '{column_name}':\n{stats.to_string()}"
    except Exception as e:
        return f"Error calculating statistics: {str(e)}"


@tool
def get_column_info(column_name: str) -> str:
    """Get information about a specific column including data type and unique values.
    
    Args:
        column_name: Name of the column to analyze
        
    Returns:
        Information about the column
    """
    try:
        if column_name not in current_df.columns:
            return f"Column '{column_name}' not found."
        
        col = current_df[column_name]
        info = f"Column: {column_name}\n"
        info += f"Data Type: {col.dtype}\n"
        info += f"Non-null Count: {col.notna().sum()}\n"
        info += f"Unique Values: {col.nunique()}\n"
        if col.nunique() <= 10:
            info += f"Values: {col.unique().tolist()}"
        return info
    except Exception as e:
        return f"Error getting column info: {str(e)}"


def generate_insights(df: pd.DataFrame) -> Optional[str]:
    global current_df
    current_df = df
    
    # Initialize Azure OpenAI LLM with LangChain
    llm = AzureChatOpenAI(
        azure_endpoint=AI_ENDPOINT,
        api_key=AI_API_KEY,
        api_version="2024-10-21",
        deployment_name=MODEL,
        temperature=0.5
    )
    
    # Bind tools to the model
    tools = [get_data_summary, calculate_column_statistics, get_column_info]
    llm_with_tools = llm.bind_tools(tools)
    
    try:
        # Invoke the model with a system message and user query
        messages = [
            SystemMessage(content=INSIGHTS_SYSTEM),
            HumanMessage(content=INSIGHTS_HUMAN),
        ]
        
        print("Generating insights with tool calling...\n")
        
        # Agentic loop - continue until model generates text (not just tool calls)
        max_iterations = 10
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            print(f"--- Iteration {iteration} ---")
            
            response = llm_with_tools.invoke(messages)
            messages.append(response)
            
            print(f"DEBUG - Finish Reason: {response.response_metadata.get('finish_reason', 'unknown')}")
            print(f"DEBUG - Has tool_calls: {bool(response.tool_calls)}")
            print(f"DEBUG - Content length: {len(response.content)}")
            
            # Check if the model wants to use tools
            if response.tool_calls:
                print(f"AI is calling {len(response.tool_calls)} tools...\n")
                
                # Execute each tool call
                available_tools = {
                    "get_data_summary": get_data_summary,
                    "calculate_column_statistics": calculate_column_statistics,
                    "get_column_info": get_column_info
                }
                
                tool_executed = False
                for tool_call in response.tool_calls:
                    tool_name = tool_call['name']
                    tool_args = tool_call['args']
                    print(f"Calling tool: {tool_name} with args: {tool_args}")
                    
                    try:
                        # Execute the tool
                        tool_function = available_tools[tool_name]
                        tool_result = tool_function.invoke(tool_args)
                        print(f"Tool result received ({len(str(tool_result))} chars)\n")
                        tool_executed = True
                        
                        # Add tool result to messages
                        messages.append(
                            ToolMessage(
                                content=str(tool_result),
                                tool_call_id=tool_call['id']
                            )
                        )
                    except Exception as tool_error:
                        print(f"Tool execution error: {tool_error}\n")
                        messages.append(
                            ToolMessage(
                                content=f"Error executing tool: {str(tool_error)}",
                                tool_call_id=tool_call['id']
                            )
                        )
                
                # If no tools were successfully executed, break to avoid infinite loop
                if not tool_executed:
                    print("No tools were successfully executed. Breaking loop.\n")
                    break
            else:
                # Model generated text content without requesting tools
                print("Model has completed analysis.\n")
                break
        
        # Display final insights
        print("\n" + "="*50)
        print("AI Insights:")
        print("="*50 + "\n")

        # Extract and return the last AI message with content
        final_insights: Optional[str] = None
        for msg in reversed(messages):
            if hasattr(msg, 'content') and msg.content and msg.__class__.__name__ == 'AIMessage':
                final_insights = msg.content
                print(final_insights)
                break
        else:
            print("No text response generated from AI model.")

        return final_insights

    except Exception as e:
        import traceback
        print(f"Error: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return None


def main():
    df = download_csv()
    print(f"Loaded {len(df)} rows, {len(df.columns)} columns.\n")
    insights = generate_insights(df)
    if insights:
        send_insights_email(insights, csv_name=CSV_BLOB_NAME)


if __name__ == "__main__":
    main()
