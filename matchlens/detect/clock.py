"""Clock label for a point expressed as in-period seconds."""
from .. import config
from ..normalise import clock_label


def label_for_period_second(period: int, seconds: float) -> str:
    """Label for the minute that ends at `seconds` into the period (600 s -> 10th minute)."""
    minute = config.PERIOD_OFFSET_SECONDS[period] // 60 + max(int(seconds // 60) - 1, 0)
    return clock_label(period, minute)[0]
