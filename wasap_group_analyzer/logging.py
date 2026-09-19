from functools import wraps
import time

from loguru import logger


def log_execution(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()

        with logger.contextualize(job=func.__qualname__):
            logger.info("Starting")

            try:
                result = func(*args, **kwargs)
            except Exception:
                logger.exception("Failed")
                raise

            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info("Completed in {:.2f} ms", elapsed_ms)

            return result

    return wrapper
