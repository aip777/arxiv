import re
import sys
import traceback as tb_module

SENSITIVE_PATTERN = re.compile(
    r'(password|passwd|token|secret|api[_-]?key|authorization|credit.card|ssn)'
    r'["\']?\s*[:=]\s*["\']?[^\s,;"\'}\]]+',
    re.IGNORECASE,
)

SENSITIVE_REPLACEMENT = r'\1=***FILTERED***'


def sanitize_text(text):
    if not isinstance(text, str):
        return str(text)
    return SENSITIVE_PATTERN.sub(SENSITIVE_REPLACEMENT, text)


def extract_request_info(request):
    if not request:
        return None, None, None
    path = getattr(request, 'path', None)
    method = getattr(request, 'method', None)
    user = None
    try:
        req = getattr(request, '_request', request)
        if hasattr(req, 'user') and req.user.is_authenticated:
            user = str(req.user)
    except Exception:
        pass
    return path, method, user


def create_error_log(level, message, exc=None, path=None, method=None, user=None, status_code=None):
    try:
        from basebox.models.error_log import ErrorLog

        trace = None
        if exc:
            trace = sanitize_text(
                ''.join(tb_module.format_exception(type(exc), exc, exc.__traceback__))
            )

        ErrorLog.objects.create(
            level=level,
            message=sanitize_text(str(message))[:2000],
            traceback=trace[:10000] if trace else None,
            path=str(path)[:500] if path else None,
            method=str(method)[:10] if method else None,
            user=str(user)[:150] if user else None,
            status_code=status_code,
        )
    except Exception as e:
        print(f"[ErrorLog] Failed to write: {e}", file=sys.stderr)
