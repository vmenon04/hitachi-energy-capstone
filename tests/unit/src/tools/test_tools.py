import pytest
import pandas as pd
from src.tools.tools import get_tools


PRIMARY_FILE = 'Project_Data/file1.csv'


@pytest.fixture
def sample_dataframe():
    """Create a mock DataFrame for testing"""
    return pd.DataFrame({
        'id': [1, 2, 3, 4, 5],
        'name': ['Alice', 'Bob', 'Charlie', 'David', 'Eve'],
        'age': [25, 30, 35, 40, 45],
        'salary': [50000.0, 60000.0, 75000.0, 80000.0, 90000.0],
        'department': ['Sales', 'IT', 'Sales', 'HR', 'IT']
    })


@pytest.fixture
def tools(sample_dataframe):
    """Get tools initialized with sample data"""
    test_dfs = {
        'Project_Data/file1.csv': sample_dataframe,
        'Project_Data/extra.csv': sample_dataframe.head(2),
    }
    return {tool.name: tool for tool in get_tools(test_dfs)}


class TestGetFiles:
    def test_returns_all_csv_filenames(self, tools):
        """Test that get_files returns all available CSV filenames"""
        result = tools['get_files'].invoke({})
        assert 'List of CSV Files:' in result
        assert 'Project_Data/file1.csv' in result
        assert 'Project_Data/extra.csv' in result


class TestGetDataSummary:
    def test_returns_summary_string(self, tools):
        """Test that get_data_summary returns formatted summary"""
        result = tools['get_data_summary'].invoke({'filename': PRIMARY_FILE})
        assert 'Shape: 5 rows, 5 columns' in result
        assert 'Columns:' in result
        assert 'Column types:' in result

    def test_summary_contains_all_columns(self, tools):
        """Test that summary includes all column names"""
        result = tools['get_data_summary'].invoke({'filename': PRIMARY_FILE})
        assert 'id' in result
        assert 'name' in result
        assert 'age' in result
    
    def test_invalid_file(self, tools):
        """Test that error message pops up if we try to use an invalid file"""
        result = tools['get_data_summary'].invoke({'filename': 'fake.csv'})
        assert 'Error getting data summary' in result


class TestCalculateColumnStatistics:
    def test_numeric_column_statistics(self, tools):
        """Test statistics calculation for numeric column"""
        result = tools['calculate_column_statistics'].invoke({'filename': PRIMARY_FILE, 'column_name': 'age'})
        assert 'Statistics for' in result
        assert 'mean' in result.lower()
        assert 'std' in result.lower()

    def test_invalid_column_name(self, tools):
        """Test error handling for non-existent column"""
        result = tools['calculate_column_statistics'].invoke({'filename': PRIMARY_FILE, 'column_name': 'invalid_col'})
        assert 'not found' in result
        assert 'Available columns:' in result

    def test_statistics_accuracy(self, tools):
        """Test that statistics values are calculated correctly"""
        result = tools['calculate_column_statistics'].invoke({'filename': PRIMARY_FILE, 'column_name': 'age'})
        assert '25' in result  # min value
        assert '45' in result  # max value (should appear in result)


class TestGetColumnInfo:
    def test_numeric_column_info(self, tools):
        """Test info for numeric column"""
        result = tools['get_column_info'].invoke({'filename': PRIMARY_FILE, 'column_name': 'salary'})
        assert 'Column: salary' in result
        assert 'Data Type: float' in result
        assert 'Non-null Count: 5' in result

    def test_string_column_info(self, tools):
        """Test info for string column"""
        result = tools['get_column_info'].invoke({'filename': PRIMARY_FILE, 'column_name': 'name'})
        assert 'Column: name' in result
        assert 'Unique Values: 5' in result
        assert 'Data Type: str' in result or 'Data Type: object' in result

    def test_missing_column_error(self, tools):
        """Test error handling for missing column"""
        result = tools['get_column_info'].invoke({'filename': PRIMARY_FILE, 'column_name': 'nonexistent'})
        assert 'not found' in result

    def test_unique_values_display(self, tools):
        """Test that unique values are displayed for columns with ≤10 unique values"""
        result = tools['get_column_info'].invoke({'filename': PRIMARY_FILE, 'column_name': 'department'})
        assert 'Values:' in result
        assert 'Sales' in result
        assert 'IT' in result

class TestGetValueCounts:
    """Tests the get_value_counts output"""
    def test_value_counts(self, tools):
        result = tools['get_value_counts'].invoke({'filename': PRIMARY_FILE, 'column_name': 'department', 'top_n': 10})
        assert 'Value counts for' in result
        assert 'Sales' in result
        assert 'IT' in result
    
    def test_invalid_column(self, tools):
        """Tests get_value_counts with invalid input"""
        result = tools['get_value_counts'].invoke({'filename': PRIMARY_FILE, 'column_name': 'invalid', 'top_n': 10})
        assert 'not found' in result
        assert 'Available columns:' in result

class TestFilterRows:
    def test_filter_rows_equal(self, tools):
        """Tests filter_rows for the equal operation"""
        result = tools['filter_rows'].invoke({'filename': PRIMARY_FILE, 'column_name': 'department', 'operator': '==', 'value': 'Sales'})
        assert '2 matching rows' in result

    def test_filter_rows_not_equal(self, tools):
        """Tests filter_rows for the not equal operation"""
        result = tools['filter_rows'].invoke({'filename': PRIMARY_FILE, 'column_name': 'department', 'operator': '!=', 'value': 'Sales'})
        assert '3 matching rows' in result

    def test_filter_rows_greater(self, tools):
        """Tests filter_rows for the greater than operation"""
        result = tools['filter_rows'].invoke({'filename': PRIMARY_FILE, 'column_name': 'age', 'operator': '>', 'value': '30'})
        assert '3 matching rows' in result

    def test_filter_rows_less(self, tools):
        """Tests filter_rows for the less than operation"""
        result = tools['filter_rows'].invoke({'filename': PRIMARY_FILE, 'column_name': 'age', 'operator': '<', 'value': '30'})
        assert '1 matching rows' in result

    def test_filter_rows_greater_equal(self, tools):
        """Tests filter_rows for the greater than or equal operation"""
        result = tools['filter_rows'].invoke({'filename': PRIMARY_FILE, 'column_name': 'age', 'operator': '>=', 'value': '30'})
        assert '4 matching rows' in result

    def test_filter_rows_less_equal(self, tools):
        """Tests filter_rows for the less than or equal operation"""
        result = tools['filter_rows'].invoke({'filename': PRIMARY_FILE, 'column_name': 'age', 'operator': '<=', 'value': '30'})
        assert '2 matching rows' in result

    def test_filter_rows_contains(self, tools):
        """Tests filter_rows for the contains operation"""
        result = tools['filter_rows'].invoke({'filename': PRIMARY_FILE, 'column_name': 'name', 'operator': 'contains', 'value': 'a'})
        assert 'matching rows' in result

    def test_filter_rows_isnull(self, tools):
        """Tests filter_rows for the isnull operation"""
        result = tools['filter_rows'].invoke({'filename': PRIMARY_FILE, 'column_name': 'age', 'operator': 'isnull', 'value': ''})
        assert '0 matching rows' in result

    def test_filter_rows_notnull(self, tools):
        """Tests filter_rows for the notnull operation"""
        result = tools['filter_rows'].invoke({'filename': PRIMARY_FILE, 'column_name': 'age', 'operator': 'notnull', 'value': ''})
        assert '5 matching rows' in result

    def test_filter_rows_invalid(self, tools):
        """Tests get_value_counts with invalid input (operators)"""
        result = tools['filter_rows'].invoke({'filename': PRIMARY_FILE, 'column_name': 'age', 'operator': '???', 'value': '30'})
        assert 'Unknown operator' in result

    def test_filter_rows_nonexistent_column(self, tools):
        """Tests get_value_counts with invalid input (columns)"""
        result = tools['filter_rows'].invoke({'filename': PRIMARY_FILE, 'column_name': 'bad', 'operator': '==', 'value': 'x'})
        assert 'not found' in result

class TestGetTopN:
    """Tests get_top_n for descending output"""
    def test_get_top_n_descending(self, tools):
        result = tools['get_top_n'].invoke({'filename': PRIMARY_FILE, 'sort_column': 'salary', 'n': 2, 'ascending': False})
        assert 'Top 2 rows' in result
        assert '90000' in result
        assert '80000' in result
    
    """Tests get_top_n for ascending output"""
    def test_get_top_n_ascending(self, tools):
        result = tools['get_top_n'].invoke({'filename': PRIMARY_FILE, 'sort_column': 'salary', 'n': 2, 'ascending': True})
        assert 'Top 2 rows' in result
        assert '50000' in result
        assert '60000' in result
    
    """Tests get_top_n for invalid parameters"""
    def test_get_top_n_invalid(self, tools):
        result = tools['get_top_n'].invoke({'filename': PRIMARY_FILE, 'sort_column': 'fake', 'n': 2, 'ascending': True})
        assert 'not found' in result
    
class TestCrossReference:
    """Tests cross_reference for joining two files by column"""
    def test_cross_reference_join(self, tools):
        result = tools['cross_reference'].invoke({'filename1': PRIMARY_FILE, 'column1': 'id', 'filename2': 'Project_Data/extra.csv', 'column2': 'id'})
        assert 'matching rows' in result

    """Tests get_top_n for valid output when missing csv files"""
    def test_cross_reference_missing_dataset(self, tools):
        result = tools['cross_reference'].invoke({'filename1': 'fake.csv', 'column1': 'id', 'filename2': 'Project_Data/extra.csv', 'column2': 'id'})
        assert 'not found' in result
