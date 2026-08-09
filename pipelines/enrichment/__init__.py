"""Aspect enrichment components for the Week 2 processing pipeline."""

from pipelines.enrichment.aspect_extractor import AspectExtractor
from pipelines.enrichment.quality_scorer import score_quality

__all__ = ["AspectExtractor", "score_quality"]
