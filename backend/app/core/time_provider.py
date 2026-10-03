"""Единый источник времени для всех сервисов.

В демо часы ресторана не идут вместе с ноутбуком. Иначе заказы, созданные
в 19:20, к 21:00 превращаются в «ждут 100 минут», а все брони уже в прошлом.

Зафиксированное время задаётся при наполнении базы (вечер перед пиком)
и читается при старте сервера.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from app.config import BACKEND_DIR

CLOCK_PATH = BACKEND_DIR / "data" / "demo_clock.json"
DEMO_HOUR = 19
DEMO_MINUTE = 20


def evening_service_time(anchor: Optional[datetime] = None) -> datetime:
    """Субботний вечер перед пиком — одна и та же сцена для любой демонстрации."""

    base = anchor or datetime.now()
    return base.replace(hour=DEMO_HOUR, minute=DEMO_MINUTE, second=0, microsecond=0)


class TimeProvider:
    def __init__(self) -> None:
        self._fixed: Optional[datetime] = None
        self._sim_time: Optional[datetime] = None
        self._speed_factor: int = 1
        self.load()

    @property
    def is_simulated(self) -> bool:
        return self._sim_time is not None

    @property
    def speed_factor(self) -> int:
        return self._speed_factor

    def now(self) -> datetime:
        if self._sim_time is not None:
            return self._sim_time
        if self._fixed is not None:
            return self._fixed
        return datetime.now()

    def set_fixed(self, moment: datetime) -> None:
        self._fixed = moment
        CLOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        CLOCK_PATH.write_text(
            json.dumps({"now": moment.isoformat(timespec="minutes")}),
            encoding="utf-8",
        )

    def load(self) -> None:
        if not CLOCK_PATH.exists():
            return
        try:
            payload = json.loads(CLOCK_PATH.read_text(encoding="utf-8"))
            self._fixed = datetime.fromisoformat(payload["now"])
        except (json.JSONDecodeError, KeyError, ValueError):
            self._fixed = None

    def start_simulation(self, start_at: datetime, speed_factor: int = 60) -> None:
        self._sim_time = start_at
        self._speed_factor = speed_factor

    def advance(self, minutes: int) -> datetime:
        if self._sim_time is None:
            raise RuntimeError("Симуляция не запущена")
        self._sim_time += timedelta(minutes=minutes)
        return self._sim_time

    def stop_simulation(self) -> None:
        self._sim_time = None
        self._speed_factor = 1


clock = TimeProvider()
