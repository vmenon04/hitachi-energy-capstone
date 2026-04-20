import logging
import sys

class ContextFilter(logging.Filter):
    def __init__(self, job_name: str, execution_id: str):
        super().__init__()
        self.job_name = job_name
        self.execution_id = execution_id
    
    def filter(self, record: logging.LogRecord) -> bool:
        record.job_name = self.job_name
        record.execution_id = self.execution_id
        return True

def setup_logger(job_name: str, execution_id: str) -> logging.Logger:
    logger = logging.getLogger("hitachi_pipeline")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt=(
                "%(asctime)s %(levelname)s %(name)s "
                "[job=%(job_name)s execution_id=%(execution_id)s] %(message)s"
            )
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.addFilter(ContextFilter(job_name, execution_id))

    return logger


def log_section(title: str) -> None:
    line = "=" * 80
    logger = logging.getLogger("hitachi_pipeline")
    logger.info("\n%s\n%s\n%s", line, title, line)


def log_subsection(title: str) -> None:
    line = "-" * 60
    logger = logging.getLogger("hitachi_pipeline")
    logger.info("\n%s\n%s\n%s", line, title, line)


def log_iteration(iteration: int) -> None:
    line = "-" * 25
    logger = logging.getLogger("hitachi_pipeline")
    logger.info("\n%s Iteration %d %s", line, iteration, line)