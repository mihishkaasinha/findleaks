"""
Global singletons loaded at startup.
sentence-transformer model and FAISS indexes are loaded ONCE here —
never instantiated per-request.
"""
from typing import Any

faiss_indexes: dict[str, Any] = {}
sentence_model: Any = None
scanner_threads: dict[str, Any] = {}
question_bank: dict[str, list[str]] = {}  # exam_slug -> ordered list of question texts
