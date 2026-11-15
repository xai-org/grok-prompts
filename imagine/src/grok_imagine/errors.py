"""Failures a caller can show to a person. Messages must not contain the API key."""


class ImagineError(Exception):
    """A request was not sent, or the image API rejected it."""


class ImagineApiError(ImagineError):
    """The image API returned a non-success HTTP status."""

    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail
        super().__init__(f"Image API request failed ({status}): {detail}")
