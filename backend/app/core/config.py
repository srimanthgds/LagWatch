import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "InsulGuard 4.0"
    API_V1_STR: str = "/api/v1"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./insulguard.db")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "insulguard-cui-super-secret-key-4.0-industrial")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    
    # Corrosion & Physics defaults
    DEFAULT_CR0_MM_YR: float = 0.35  # Base corrosion rate in mm/yr
    DEFAULT_CHLORIDE_FACTOR: float = 1.0
    MOISTURE_THRESHOLD_PCT: float = 10.0
    DELTA_T_THRESHOLD_C: float = 6.0
    WALL_LOSS_VERIFY_THRESHOLD_PCT: float = 25.0
    REMAINING_LIFE_PLAN_REPAIR_YR: float = 2.0
    IMMINENT_MARGIN_MM: float = 0.5
    
    # Financial baseline
    BASELINE_ANNUAL_LOSS_USD: float = 26_800_000.0
    DEFAULT_CAPEX_USD: float = 12_513_000.0
    DEFAULT_OPEX_USD_YR: float = 1_850_000.0
    DEFAULT_DISCOUNT_RATE: float = 0.08
    DEFAULT_BENEFIT_CAPTURE_PCT: float = 0.65  # 65% loss reduction

    class Config:
        env_file = ".env"

settings = Settings()
