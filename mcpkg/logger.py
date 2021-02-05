import sys

from .cli import config
from .constants import LogLevel


def log(message: str, level: LogLevel) -> None:
    """Log a provided message to stderr."""
    if level is LogLevel.DEBUG and not config.verbose:
        return
    print(f"{level.value} {message}", file=sys.stderr)