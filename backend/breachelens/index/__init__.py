"""BreachLens index layer (FTS5 + structured records)."""
from .query import SearchRequest, execute_search, detect_query_type

__all__ = ["SearchRequest", "execute_search", "detect_query_type"]
