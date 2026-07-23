"""BreachLens configuration loaded from environment + defaults."""
from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerConfig(BaseSettings):
    bind_addr: str = "127.0.0.1"
    port: int = 8443
    cors_origins: List[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    max_request_size_mb: int = 4


class StorageConfig(BaseSettings):
    data_dir: Path = Path.home() / ".local" / "share" / "breachelens"
    index_dir: Path = Path.home() / ".local" / "share" / "breachelens" / "index"
    db_path: Path = Path.home() / ".local" / "share" / "breachelens" / "breachelens.db"
    default_mode: str = "offset"  # offset | full


class IndexingConfig(BaseSettings):
    max_workers: int = 4
    max_file_size_mb: int = 2048
    max_line_length: int = 65536
    batch_size: int = 4096
    encoding_fallback: str = "latin-1"
    skip_unchanged: bool = True


class SearchConfig(BaseSettings):
    max_concurrent: int = 4
    max_results_per_query: int = 1000
    query_timeout_ms: int = 30_000
    max_preview_length: int = 256
    rate_limit_per_minute: int = 60


class RegexSafetyConfig(BaseSettings):
    max_pattern_length: int = 256
    max_execution_ms: int = 5_000
    max_backtracks: int = 1_000_000
    max_candidate_files: int = 500
    block_catastrophic: bool = True
    anchor_by_default: bool = True


class AuthConfig(BaseSettings):
    session_lifetime_secs: int = 8 * 3600
    auto_lock_idle_secs: int = 15 * 60
    reauth_on_reveal: bool = True
    reauth_on_export: bool = True
    allow_reveal: bool = True


class AuditConfig(BaseSettings):
    hash_algorithm: str = "sha256"
    sign_with_operator_key: bool = True
    replicate_to_syslog: bool = False


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BREACHLENS_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    server: ServerConfig = Field(default_factory=ServerConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    indexing: IndexingConfig = Field(default_factory=IndexingConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    regex_safety: RegexSafetyConfig = Field(default_factory=RegexSafetyConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)

    @classmethod
    def load(cls) -> "Config":
        return cls()


def load_config() -> Config:
    return Config.load()
