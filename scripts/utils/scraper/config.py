import os
from dataclasses import dataclass


@dataclass
class Config:
    supabase_url: str = os.environ.get("SUPABASE_URL", "")
    supabase_key: str = os.environ.get("SUPABASE_SERVICE_KEY", "")


config = Config()
