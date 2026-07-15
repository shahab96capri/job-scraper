"""Pipeline layer: orchestrates Spider -> Parser -> Normalizer -> Validator
-> Repository for a full crawl run. Depends only on layer abstractions
(Dependency Injection) so it is testable without any concrete site
implementation."""

from app.pipelines.job_pipeline import JobIngestionPipeline

__all__ = ["JobIngestionPipeline"]
