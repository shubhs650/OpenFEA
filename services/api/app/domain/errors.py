"""Public domain failures with no database or filesystem details."""


class DomainError(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable


def not_found() -> DomainError:
    return DomainError(404, "not_found", "The requested object is unavailable")


def stale_revision() -> DomainError:
    return DomainError(409, "stale_revision", "This revision changed; reload before saving")
