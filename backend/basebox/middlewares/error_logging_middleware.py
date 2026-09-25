from basebox.utils.error_logger import create_error_log, extract_request_info


class ErrorLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if response.status_code >= 400 and not getattr(request, "_error_logged", False):
            path, method, user = extract_request_info(request)
            level = "ERROR" if response.status_code >= 500 else "WARNING"
            message = getattr(response, "reason_phrase", f"HTTP {response.status_code}")

            create_error_log(
                level=level,
                message=message,
                path=path,
                method=method,
                user=user,
                status_code=response.status_code,
            )

        return response

    def process_exception(self, request, exception):
        if getattr(request, "_error_logged", False):
            return None

        request._error_logged = True
        path, method, user = extract_request_info(request)

        create_error_log(
            level="ERROR",
            message=str(exception),
            exc=exception,
            path=path,
            method=method,
            user=user,
            status_code=500,
        )
        return None
