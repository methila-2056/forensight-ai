"""Evidence-traceable AI investigation assistant (Phase 5).

Deterministic, retrieval-first answer generation over the persisted Phase 0-4
pipeline output. No generative model is involved: every answer is composed
from parameterized, case-scoped queries against the database.
"""

from app.assistant.intents import Intent, classify
from app.assistant.service import answer_question, get_query, history

__all__ = ["Intent", "classify", "answer_question", "get_query", "history"]