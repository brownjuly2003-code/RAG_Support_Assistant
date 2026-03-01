# ingestion/__init__.py

"""
Document ingestion package.

Modules:
    loader   -- DocumentLoader: load files (.txt, .md, .pdf, .docx, .json, .csv)
    pipeline -- IngestPipeline: load + build vector store + log metadata
"""

from ingestion.loader import DocumentLoader, SUPPORTED_EXTENSIONS
from ingestion.pipeline import IngestPipeline

__all__ = [
    "DocumentLoader",
    "IngestPipeline",
    "SUPPORTED_EXTENSIONS",
]
