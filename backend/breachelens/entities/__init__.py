"""BreachLens entity extraction."""
from .detectors import (
    DetectedHash,
    DetectedSecret,
    ExtractedEntities,
    NormalizedUrl,
    extract,
)
from .dedupe import DedupeHashes, compute_hashes, query_hash
from .endpoint_classifier import classify_endpoint
from .service_classifier import classify_service, default_service_mappings, populate_cache as populate_service_cache
from .url_normalizer import normalize, split_domain

__all__ = [
    "DetectedHash",
    "DetectedSecret",
    "ExtractedEntities",
    "NormalizedUrl",
    "extract",
    "DedupeHashes",
    "compute_hashes",
    "query_hash",
    "classify_endpoint",
    "classify_service",
    "default_service_mappings",
    "populate_service_cache",
    "normalize",
    "split_domain",
]
