"""Deterministic normalization layer — no LLM calls.

Everything in this package is pure code that runs in BOTH the standard and pro
pipeline profiles, because it costs nothing. It exists to remove the classes of
output defect that come from faithfully reproducing whatever inconsistency was
in the raw input:

  - dates:    "June 2022" beside "Jun 2022" beside "06/2022" in one document
  - ordering: entries presented in relevance order instead of reverse-chronological
  - skills:   free-text LLM category names that change from run to run
"""
