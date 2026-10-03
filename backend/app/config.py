from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI Restaurant Manager"
    restaurant_name: str = "Терра"
    seats_total: int = 200
    interface_language: str = "ru"

    database_path: Path = BACKEND_DIR / "data" / "restaurant.db"

    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    ai_enabled: bool = True
    ai_temperature: float = 0.2
    ai_timeout_seconds: int = 20

    # Пороги движка правил. Проблема фиксируется кодом, а не моделью.
    kitchen_load_warning_pct: int = 70
    kitchen_load_critical_pct: int = 85
    wait_warning_min: int = 18
    wait_critical_min: int = 25
    staff_load_warning_pct: int = 80
    reservation_spike_count: int = 6

    forecast_horizons_min: tuple = (30, 60)
    impact_window_min: int = 20

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"

    @property
    def ai_available(self) -> bool:
        return self.ai_enabled and bool(self.openai_api_key)


settings = Settings()
settings.database_path.parent.mkdir(parents=True, exist_ok=True)
