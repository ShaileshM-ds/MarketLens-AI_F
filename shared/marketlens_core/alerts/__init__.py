"""Watchlists, target-price alert rules, evaluation and in-app notifications (Phase 5)."""


class AlertError(Exception):
    """A request that can't be carried out, with an HTTP-style status and a plain message."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message
