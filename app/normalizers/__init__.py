"""Normalizer layer: maps raw site-specific values onto standard platform
values. See `base_normalizer.py` for the contract."""

from app.normalizers.base_normalizer import BaseNormalizer
from app.normalizers.jobvision_normalizer import JobVisionNormalizer

__all__ = ["BaseNormalizer", "JobVisionNormalizer"]
