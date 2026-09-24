import logging

from basebox.utils.error_logger import create_error_log


class LogHandler(logging.Handler):
    """Stores ERROR log records in the ErrorLog table so they show up in the admin."""

    def emit(self, record):
        try:
            exc = record.exc_info[1] if record.exc_info else None
            create_error_log(level=record.levelname, message=self.format(record), exc=exc)
        except Exception:
            self.handleError(record)
