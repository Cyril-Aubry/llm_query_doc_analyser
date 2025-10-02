"""
Embedding-based semantic similarity filtering (DEPRECATED).

This module is deprecated in favor of LLM-based filtering in prompts.py.
It is kept for backward compatibility and reference purposes only.
"""
import os

from sentence_transformers import SentenceTransformer, util

MODEL_NAME = os.getenv("EMBED_MODEL", "sentence-transformers/all-mpnet-base-v2")
_model = None

def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model

def encode(texts: list[str]):
    model = get_model()
    return model.encode(texts, convert_to_tensor=True)

def similarity(query: str, docs: list[str]) -> list[float]:
    model = get_model()
    q_emb = model.encode([query], convert_to_tensor=True)
    d_emb = model.encode(docs, convert_to_tensor=True)
    sims = util.pytorch_cos_sim(q_emb, d_emb)[0].cpu().numpy()
    return sims.tolist()
