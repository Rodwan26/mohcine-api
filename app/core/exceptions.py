from fastapi import HTTPException, status


class AppException(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, details: dict | None = None):
        super().__init__(status_code=status_code, detail={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        })


class NotFound(AppException):
    def __init__(self, message: str = "Resource not found", details: dict | None = None):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, code="NOT_FOUND", message=message, details=details)


class Conflict(AppException):
    def __init__(self, message: str = "Resource already exists", details: dict | None = None):
        super().__init__(status_code=status.HTTP_409_CONFLICT, code="CONFLICT", message=message, details=details)


class Unauthorized(AppException):
    def __init__(self, message: str = "Unauthorized", details: dict | None = None):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, code="UNAUTHORIZED", message=message, details=details)


class ValidationError(AppException):
    def __init__(self, message: str = "Validation failed", details: dict | None = None):
        super().__init__(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, code="VALIDATION_ERROR", message=message, details=details)
