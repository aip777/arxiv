import logging
from basebox.utils.error_logger import sanitize_text, create_error_log


class LogHandler(logging.Handler):
    def emit(self, record):
        try:
            trace_exc = None
            if record.exc_info and record.exc_info[1]:
                trace_exc = record.exc_info[1]

            message = sanitize_text(self.format(record))

            path = getattr(record, 'request_path', None)
            method = getattr(record, 'request_method', None)
            user = getattr(record, 'request_user', None)
            status_code = getattr(record, 'status_code', None)

            if hasattr(record, 'status_code'):
                path = path or getattr(record, 'path', None)

            create_error_log(
                level=record.levelname,
                message=message,
                exc=trace_exc,
                path=path,
                method=method,
                user=user,
                status_code=status_code,
            )
        except Exception:
            self.handleError(record)
