from langchain.tools import tool
import pandas as pd

_MAX_TOOL_OUTPUT_CHARS = 6000


def _truncate(text: str) -> str:
    """Cap tool output to avoid flooding the model context with large dataframe dumps."""
    if len(text) <= _MAX_TOOL_OUTPUT_CHARS:
        return text
    return text[:_MAX_TOOL_OUTPUT_CHARS] + f"\n... [truncated -- {len(text) - _MAX_TOOL_OUTPUT_CHARS} chars omitted]"


def get_tools(dfs: dict):

    @tool
    def get_files() -> str:
        """Get a list all CSV filenames that the model has access to

        Returns:
            A string containing the list of CSV files
        """
        summary = f"List of CSV Files:\n"
        for name in dfs.keys():
            summary += f"{name}\n"
        return summary

    @tool
    def get_data_summary(filename: str) -> str:
        """Get a summary of the CSV data including shape, columns, and first few rows.
        
        Args:
            filename: Name of the CSV file to analyze

        Returns:
            A string summary of the CSV file
        """
        try:
            df = dfs[filename]
            summary = f"CSV Data Summary:\n"
            summary += f"Shape: {df.shape[0]} rows, {df.shape[1]} columns\n"
            summary += f"Columns: {', '.join(df.columns.tolist())}\n"
            summary += f"\nColumn types:\n{df.dtypes.to_string()}"
            return summary
        except Exception as e:
            return f"Error getting data summary: {str(e)}"


    @tool
    def calculate_column_statistics(filename: str, column_name: str) -> str:
        """Calculate basic statistics for a numeric column in the CSV file.
        
        Args:
            filename: Name of the CSV file to analyze
            column_name: Name of the column to analyze
            
        Returns:
            Statistical summary of the column
        """
        try:
            df = dfs[filename]
            if column_name not in df.columns:
                return f"Column '{column_name}' not found. Available columns: {', '.join(df.columns.tolist())}"
            
            stats = df[column_name].describe()
            return f"Statistics for '{column_name}':\n{stats.to_string()}"
        except Exception as e:
            return f"Error calculating statistics: {str(e)}"


    @tool
    def get_column_info(filename: str, column_name: str) -> str:
        """Get information about a specific column including data type and unique values.
        
        Args:
            filename: Name of the CSV file to analyze
            column_name: Name of the column to analyze
            
        Returns:
            Information about the column
        """
        try:
            df = dfs[filename]
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

    @tool
    def get_value_counts(filename: str, column_name: str, top_n: int = 20) -> str:
        """Get the frequency distribution of values in a categorical column.

        Useful for understanding status breakdowns, priority distributions,
        severity splits, owner workloads, etc.

        Args:
            filename: Name of the CSV file to analyze
            column_name: Name of the column to count
            top_n: Maximum number of entries to return (default 20)

        Returns:
            Value counts sorted by frequency, descending
        """
        try:
            df = dfs[filename]
            if column_name not in df.columns:
                return f"Column '{column_name}' not found. Available columns: {', '.join(df.columns.tolist())}"
            counts = df[column_name].value_counts(dropna=False).head(top_n)
            return f"Value counts for '{column_name}' in {filename}:\n{counts.to_string()}"
        except Exception as e:
            return f"Error getting value counts: {str(e)}"

    @tool
    def filter_rows(filename: str, column_name: str, operator: str, value: str, max_rows: int = 20) -> str:
        """Filter rows in a dataset and return matching records.

        Use this to drill into specific subsets -- e.g. overdue tasks, open issues,
        high-severity risks, blocked resources.

        Args:
            filename: Name of the CSV file to analyze
            column_name: Column to filter on
            operator: One of: '==', '!=', '>', '<', '>=', '<=', 'contains', 'isnull', 'notnull'
            value: Value to compare against (ignored for isnull/notnull)
            max_rows: Maximum rows to return (default 20)

        Returns:
            Matching rows as a string table, plus count of total matches
        """
        try:
            df = dfs[filename]
            if column_name not in df.columns:
                return f"Column '{column_name}' not found. Available columns: {', '.join(df.columns.tolist())}"
            col = df[column_name]
            if operator == '==':
                mask = col == value
            elif operator == '!=':
                mask = col != value
            elif operator == '>':
                mask = pd.to_numeric(col, errors='coerce') > float(value)
            elif operator == '<':
                mask = pd.to_numeric(col, errors='coerce') < float(value)
            elif operator == '>=':
                mask = pd.to_numeric(col, errors='coerce') >= float(value)
            elif operator == '<=':
                mask = pd.to_numeric(col, errors='coerce') <= float(value)
            elif operator == 'contains':
                mask = col.astype(str).str.contains(value, case=False, na=False)
            elif operator == 'isnull':
                mask = col.isnull()
            elif operator == 'notnull':
                mask = col.notnull()
            else:
                return f"Unknown operator '{operator}'. Use: ==, !=, >, <, >=, <=, contains, isnull, notnull"
            filtered = df[mask]
            total = len(filtered)
            sample = filtered.head(max_rows)
            return _truncate(f"Filter '{column_name} {operator} {value}': {total} matching rows (showing {len(sample)}):\n{sample.to_string()}")
        except Exception as e:
            return f"Error filtering rows: {str(e)}"

    @tool
    def get_top_n(filename: str, sort_column: str, n: int = 10, ascending: bool = False) -> str:
        """Return the top N rows sorted by a numeric column.

        Use this to identify the worst offenders -- e.g. tasks with the most slip days,
        issues with the highest impact, resources with the most allocated hours.

        Args:
            filename: Name of the CSV file to analyze
            sort_column: Column to sort by
            n: Number of rows to return (default 10)
            ascending: Sort ascending if True, descending if False (default False)

        Returns:
            Top N rows as a string table
        """
        try:
            df = dfs[filename]
            if sort_column not in df.columns:
                return f"Column '{sort_column}' not found. Available columns: {', '.join(df.columns.tolist())}"
            numeric = pd.to_numeric(df[sort_column], errors='coerce')
            sorted_df = df.assign(**{sort_column: numeric}).dropna(subset=[sort_column])
            sorted_df = sorted_df.sort_values(sort_column, ascending=ascending).head(n)
            direction = "ascending" if ascending else "descending"
            return _truncate(f"Top {n} rows from '{filename}' sorted by '{sort_column}' ({direction}):\n{sorted_df.to_string()}")
        except Exception as e:
            return f"Error getting top N: {str(e)}"

    @tool
    def cross_reference(filename1: str, column1: str, filename2: str, column2: str, filter_column: str = "", filter_value: str = "") -> str:
        """Join two datasets on matching columns to find cross-dataset relationships.

        Use this to answer questions like:
        - Which projects have the most overdue tasks?
        - Which people are assigned to the most blocked tasks?
        - Which projects have the highest-severity open issues?

        Args:
            filename1: Primary dataset (e.g. tasks.csv)
            column1: Join key in filename1 (e.g. project_id)
            filename2: Secondary dataset (e.g. projects.csv)
            column2: Join key in filename2 (e.g. project_id)
            filter_column: Optional column in filename1 to filter before joining
            filter_value: Value to match in filter_column (equality check)

        Returns:
            Merged rows as a string table (up to 20 rows)
        """
        try:
            df1 = dfs.get(filename1)
            df2 = dfs.get(filename2)
            if df1 is None:
                return f"Dataset '{filename1}' not found."
            if df2 is None:
                return f"Dataset '{filename2}' not found."
            if column1 not in df1.columns:
                return f"Column '{column1}' not found in '{filename1}'."
            if column2 not in df2.columns:
                return f"Column '{column2}' not found in '{filename2}'."
            if filter_column and filter_column in df1.columns and filter_value:
                df1 = df1[df1[filter_column] == filter_value]
            merged = df1.merge(df2, left_on=column1, right_on=column2, how="inner", suffixes=("_left", "_right"))
            total = len(merged)
            sample = merged.head(20)
            return _truncate(f"Cross-reference '{filename1}'.{column1} → '{filename2}'.{column2}: {total} matching rows (showing {min(20, total)}):\n{sample.to_string()}")
        except Exception as e:
            return f"Error cross-referencing: {str(e)}"

    @tool
    def cross_reference_n(base_filename: str, joins: list[dict], max_rows: int = 20) -> str:
        """Join an arbitrary number of datasets using a sequence of join steps.

        Args:
            base_filename: Starting dataset name
            joins: Ordered join step definitions, where each step includes:
                - filename: Dataset to join next
                - left_on: Join key in current merged dataframe
                - right_on: Join key in the next dataset
                - how: Optional join type: inner, left, right, outer (default inner)
                - filter_column: Optional filter column in the next dataset
                - filter_value: Optional equality value for filter_column
            max_rows: Maximum rows to return (default 20)

        Returns:
            Merged rows as a string table, plus count of total matches
        """
        try:
            if not joins:
                return "No joins provided. Add at least one join step."

            base_df = dfs.get(base_filename)
            if base_df is None:
                return f"Dataset '{base_filename}' not found."

            merged = base_df
            allowed_join_types = {"inner", "left", "right", "outer"}

            for idx, step in enumerate(joins, start=1):
                filename = step.get("filename")
                left_on = step.get("left_on")
                right_on = step.get("right_on")
                how = step.get("how", "inner")
                filter_column = step.get("filter_column", "")
                filter_value = step.get("filter_value", "")

                if not filename or not left_on or not right_on:
                    return (
                        f"Join step {idx} is missing required fields. "
                        "Each step must include: filename, left_on, right_on."
                    )

                next_df = dfs.get(filename)
                if next_df is None:
                    return f"Join step {idx}: dataset '{filename}' not found."
                if left_on not in merged.columns:
                    return f"Join step {idx}: left key '{left_on}' not found in merged data."
                if right_on not in next_df.columns:
                    return f"Join step {idx}: right key '{right_on}' not found in '{filename}'."
                if how not in allowed_join_types:
                    return (
                        f"Join step {idx}: invalid join type '{how}'. "
                        "Use one of: inner, left, right, outer."
                    )

                if filter_column and filter_value:
                    if filter_column not in next_df.columns:
                        return (
                            f"Join step {idx}: filter column '{filter_column}' "
                            f"not found in '{filename}'."
                        )
                    next_df = next_df[next_df[filter_column] == filter_value]

                merged = merged.merge(
                    next_df,
                    left_on=left_on,
                    right_on=right_on,
                    how=how,
                    suffixes=("", f"_{idx}")
                )

            total = len(merged)
            sample = merged.head(max_rows)
            return _truncate(
                f"Cross-reference across {len(joins) + 1} datasets from '{base_filename}': "
                f"{total} matching rows (showing {len(sample)}):\n{sample.to_string()}"
            )
        except Exception as e:
            return f"Error cross-referencing across N datasets: {str(e)}"

    @tool
    def search_text(filename: str, query: str, columns: str = "", case: bool = False, regex: bool = False, max_rows: int = 20) -> str:
        """Search text in one or more columns and return matching rows.

        Args:
            filename: Name of the CSV file to analyze
            query: Text or regex pattern to search for
            columns: Comma-separated list of columns to search (default searches all columns)
            case: Case-sensitive search if True (default False)
            regex: Treat query as regex if True (default False)
            max_rows: Maximum rows to return (default 20)

        Returns:
            Matching rows as a string table, plus count of total matches
        """
        try:
            df = dfs[filename]
            if not query:
                return "Search query cannot be empty."

            if columns.strip():
                search_columns = [col.strip() for col in columns.split(',') if col.strip()]
                missing = [col for col in search_columns if col not in df.columns]
                if missing:
                    return f"Column(s) not found: {', '.join(missing)}. Available columns: {', '.join(df.columns.tolist())}"
            else:
                search_columns = df.columns.tolist()

            # Build a row-level mask by checking each selected column as text.
            mask = pd.Series(False, index=df.index)
            for col in search_columns:
                col_mask = df[col].astype(str).str.contains(query, case=case, regex=regex, na=False)
                mask = mask | col_mask

            filtered = df[mask]
            total = len(filtered)
            sample = filtered.head(max_rows)
            searched = ', '.join(search_columns)
            return _truncate(
                f"Search results for '{query}' in '{filename}' (columns: {searched}; case={case}; regex={regex}): "
                f"{total} matching rows (showing {len(sample)}):\n{sample.to_string()}"
            )
        except Exception as e:
            return f"Error searching text: {str(e)}"

    return [get_files, get_data_summary, calculate_column_statistics, get_column_info,
            get_value_counts, filter_rows, get_top_n, cross_reference, cross_reference_n, search_text]