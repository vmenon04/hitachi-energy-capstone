import pytest
import pandas as pd
from src.tools.tools import get_tools


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
    return {tool.name: tool for tool in get_tools(sample_dataframe)}


class TestGetDataSummary:
    def test_returns_summary_string(self, tools):
        """Test that get_data_summary returns formatted summary"""
        result = tools['get_data_summary'].invoke({})
        assert 'Shape: 5 rows, 5 columns' in result
        assert 'Columns:' in result
        assert 'First 5 rows:' in result

    def test_summary_contains_all_columns(self, tools):
        """Test that summary includes all column names"""
        result = tools['get_data_summary'].invoke({})
        assert 'id' in result
        assert 'name' in result
        assert 'age' in result


class TestCalculateColumnStatistics:
    def test_numeric_column_statistics(self, tools):
        """Test statistics calculation for numeric column"""
        result = tools['calculate_column_statistics'].invoke({'column_name': 'age'})
        assert 'Statistics for' in result
        assert 'mean' in result.lower()
        assert 'std' in result.lower()

    def test_invalid_column_name(self, tools):
        """Test error handling for non-existent column"""
        result = tools['calculate_column_statistics'].invoke({'column_name': 'invalid_col'})
        assert 'not found' in result
        assert 'Available columns:' in result

    def test_statistics_accuracy(self, tools):
        """Test that statistics values are calculated correctly"""
        result = tools['calculate_column_statistics'].invoke({'column_name': 'age'})
        assert '25' in result  # min value
        assert '45' in result  # max value (should appear in result)


class TestGetColumnInfo:
    def test_numeric_column_info(self, tools):
        """Test info for numeric column"""
        result = tools['get_column_info'].invoke({'column_name': 'salary'})
        assert 'Column: salary' in result
        assert 'Data Type: float' in result
        assert 'Non-null Count: 5' in result

    def test_string_column_info(self, tools):
        """Test info for string column"""
        result = tools['get_column_info'].invoke({'column_name': 'name'})
        assert 'Column: name' in result
        assert 'Unique Values: 5' in result
        assert 'Data Type: str' in result or 'Data Type: object' in result

    def test_missing_column_error(self, tools):
        """Test error handling for missing column"""
        result = tools['get_column_info'].invoke({'column_name': 'nonexistent'})
        assert 'not found' in result

    def test_unique_values_display(self, tools):
        """Test that unique values are displayed for columns with ≤10 unique values"""
        result = tools['get_column_info'].invoke({'column_name': 'department'})
        assert 'Values:' in result
        assert 'Sales' in result
        assert 'IT' in result