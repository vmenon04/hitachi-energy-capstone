from langchain.tools import tool
import pandas as pd

def get_tools(dfs: dict):

    df = dfs["Project_Data/issues_and_risks.csv"]

    @tool
    def get_data_summary() -> str:
        """Get a summary of the CSV data including shape, columns, and first few rows.
        
        Returns:
            A string summary of the CSV file
        """
        try:
            summary = f"CSV Data Summary:\n"
            summary += f"Shape: {df.shape[0]} rows, {df.shape[1]} columns\n"
            summary += f"Columns: {', '.join(df.columns.tolist())}\n"
            summary += f"\nFirst 5 rows:\n{df.head().to_string()}"
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
            if column_name not in df.columns:
                return f"Column '{column_name}' not found. Available columns: {', '.join(df.columns.tolist())}"
            
            stats = df[column_name].describe()
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
            if column_name not in df.columns:
                return f"Column '{column_name}' not found."
            
            col = df[column_name]
            info = f"Column: {column_name}\n"
            info += f"Data Type: {col.dtype}\n"
            info += f"Non-null Count: {col.notna().sum()}\n"
            info += f"Unique Values: {col.nunique()}\n"
            if col.nunique() <= 10:
                info += f"Values: {col.unique().tolist()}"
            return info
        except Exception as e:
            return f"Error getting column info: {str(e)}"
        
    return [get_data_summary, calculate_column_statistics, get_column_info]