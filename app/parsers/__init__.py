"""Parser layer: extracts raw, unconverted values from HTML. See
`base_parser.py` for the contract."""

from app.parsers.base_parser import BaseParser
from app.parsers.jobvision_parser import JobVisionParser

__all__ = ["BaseParser", "JobVisionParser"]
