import logging
import pytest

from src.utils.logging_utils import (
    ContextFilter,
    log_iteration,
    log_section,
    log_subsection,
    setup_logger,
)


@pytest.fixture
def clean_pipeline_logger():
    """Reset the named logger so tests are deterministic and isolated."""
    logger = logging.getLogger("hitachi_pipeline")
    original_handlers = list(logger.handlers)
    original_filters = list(logger.filters)
    original_level = logger.level

    logger.handlers.clear()
    logger.filters.clear()
    logger.setLevel(logging.NOTSET)

    yield logger

    logger.handlers.clear()
    logger.filters.clear()
    logger.setLevel(original_level)
    for handler in original_handlers:
        logger.addHandler(handler)
    for filt in original_filters:
        logger.addFilter(filt)


class TestContextFilter:
    def test_adds_job_context_to_log_record(self):
        filt = ContextFilter(job_name="daily-report", execution_id="run-123")
        record = logging.LogRecord(
            name="hitachi_pipeline",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )

        result = filt.filter(record)

        assert result is True
        assert record.job_name == "daily-report"
        assert record.execution_id == "run-123"


class TestSetupLogger:
    def test_singleton_logger(self):
        first = setup_logger("job-a", "exec-1")
        second = setup_logger("job-b", "exec-2")

        assert first is second
        assert first.name == "hitachi_pipeline"
        assert first.level == logging.INFO
        assert len(first.handlers) == 1
        assert len(first.filters) == 1
        assert isinstance(first.filters[0], ContextFilter)


class TestLogHelpers:
    def test_log_helpers(self, caplog):
        setup_logger("daily-report", "run-001")

        with caplog.at_level(logging.INFO, logger="hitachi_pipeline"):
            log_section("Pipeline Start")
            log_subsection("Data Fetch")
            log_iteration(3)

        messages = [record.getMessage() for record in caplog.records]
        combined = "\n".join(messages)

        assert "Pipeline Start" in combined
        assert "Data Fetch" in combined
        assert "Iteration 3" in combined
