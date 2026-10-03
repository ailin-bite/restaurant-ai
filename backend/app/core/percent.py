"""Все проценты в интерфейсе и API — только от 0 до 100."""


def clamp_pct(value: float) -> float:
    if value is None:
        return 0.0
    return round(min(100.0, max(0.0, float(value))), 1)
