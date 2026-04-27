# ingestion/__init__.py

"""
Document ingestion package.

Modules:
    loader   -- DocumentLoader / DocumentChangeTracker
    pipeline -- IngestPipeline: load + build vector store + log metadata
"""

from ingestion.loader import DocumentChangeTracker, DocumentLoader, SUPPORTED_EXTENSIONS
from ingestion.pipeline import IngestPipeline

__all__ = [
    "DocumentLoader",
    "DocumentChangeTracker",
    "IngestPipeline",
    "SUPPORTED_EXTENSIONS",
]
