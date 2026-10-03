"""Единый источник времени для всех сервисов.

В обычном режиме отдаёт реальное время, в режиме симуляции — виртуальное.
Благодаря этому аналитика, прогноз и измерение результата работают в ускоренном
времени тем же кодом, без отдельной ветки логики.
"""

from datetime import datetime, timedelta
from typing import Optional


class TimeProvider:
    def __init__(self) -> None:
        self._sim_time: Optional[datetime] = None
        self._speed_factor: int = 1

    @property
    def is_simulated(self) -> bool:
        return self._sim_time is not None

    @property
    def speed_factor(self) -> int:
        return self._speed_factor

    def now(self) -> datetime:
        if self._sim_time is not None:
            return self._sim_time
        return datetime.now()

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
