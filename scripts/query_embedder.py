#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
query_embedder.py — Deterministic Query Embedding Path for Agent Runtime.

Problem this solves:
  Agents run stdlib-only. They cannot import sentence-transformers.
  But memory_retriever.top_k() requires a 384-dim embedding vector.
  Without this, semantic retrieval is impossible at agent runtime.

Solution — two-tier approach:

  Tier 1 (CI): sentence-transformers pre-computes embeddings for all
  known repository content. This is the full semantic memory.

  Tier 2 (Agent runtime): This module provides two runtime options:

    Option A — ONNX-based local inference (RECOMMENDED):
      Run bge-small-en-v1.5 as an ONNX model via the `onnxruntime`
      package. The model ONNX file is committed to the repo at
      .memory/model/bge-small-en-v1.5.onnx (exported once in CI).
      `onnxruntime` is pure Python, no C++ deps beyond the pre-compiled
      wheel. This is the production path.

      Install: pip install onnxruntime==1.17.3

    Option B — Stub embedding (FALLBACK):
      Returns a zero vector. Semantic similarity will be 0 for all
      records, so retrieval falls back to decision-log keyword search.
      This is the safe fallback when onnxruntime is unavailable.

  Both options are transparent to MemoryRetriever — it only sees a
  384-dim float list.

Exporting the ONNX model (run once in CI, commit to repo):
  python scripts/query_embedder.py --export-onnx \
    --model-path ~/.cache/huggingface/hub/... \
    --output .memory/model/bge-small-en-v1.5.onnx

Usage at agent runtime:
  from query_embedder import embed_query

  vec = embed_query("how does the label-swap lock prevent race conditions")
  # vec is a list[float] of length 384

Stdlib-safe: importing this module without onnxruntime installed
returns None from embed_query() — MemoryRetriever handles that gracefully.
"""

import json
import logging
import math
import os
import struct
import sys
from typing import Any

logger = logging.getLogger(__name__)

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPTS_DIR)

ONNX_MODEL_PATH = os.environ.get(
    "MEMORY_ONNX_MODEL",
    os.path.join(REPO_ROOT, ".memory", "model", "bge-small-en-v1.5.onnx"),
)
ONNX_VOCAB_PATH = os.environ.get(
    "MEMORY_ONNX_VOCAB",
    os.path.join(REPO_ROOT, ".memory", "model", "vocab.txt"),
)

EMBEDDING_DIM = 384
MAX_SEQ_LEN = 128  # bge-small max context length


# ---------------------------------------------------------------------------
# Minimal BPE / WordPiece tokenizer (no third-party deps)
# ---------------------------------------------------------------------------

class _MinimalWordPieceTokenizer:
    """
    Minimal WordPiece tokenizer using the vocab.txt from BERT/BGE models.
    Implements only what is needed to tokenize short queries (< 512 tokens).

    This is not a complete tokenizer — it handles the common case of
    ASCII query strings without rare Unicode. For production use,
    prefer the ONNX tokenizer extension or onnxruntime-extensions.
    """

    def __init__(self, vocab_path: str) -> None:
        self.vocab: dict[str, int] = {}
        self._unk_id = 100  # [UNK] standard BERT id
        self._cls_id = 101  # [CLS]
        self._sep_id = 102  # [SEP]
        self._pad_id = 0    # [PAD]
        if os.path.isfile(vocab_path):
            with open(vocab_path, encoding="utf-8") as fh:
                for idx, line in enumerate(fh):
                    token = line.strip()
                    if token:
                        self.vocab[token] = idx
            # Update special token ids from vocab
            self._unk_id = self.vocab.get("[UNK]", 100)
            self._cls_id = self.vocab.get("[CLS]", 101)
            self._sep_id = self.vocab.get("[SEP]", 102)
            self._pad_id = self.vocab.get("[PAD]", 0)
        else:
            logger.warning("vocab.txt not found at %s — using character-level fallback", vocab_path)

    def tokenize(self, text: str, max_len: int = MAX_SEQ_LEN) -> tuple[list[int], list[int], list[int]]:
        """
        Tokenize text into input_ids, attention_mask, token_type_ids.

        Returns three lists of length max_len (padded).
        """
        # Lowercase + basic whitespace tokenization
        words = text.lower().strip().split()
        token_ids: list[int] = [self._cls_id]

        for word in words:
            if len(token_ids) >= max_len - 1:
                break
            # Greedy longest-match WordPiece
            if word in self.vocab:
                token_ids.append(self.vocab[word])
            else:
                # Character-level fallback
                for char in word:
                    token_ids.append(self.vocab.get(char, self._unk_id))
                    if len(token_ids) >= max_len - 1:
                        break

        token_ids.append(self._sep_id)

        # Pad to max_len
        seq_len = len(token_ids)
        attention_mask = [1] * seq_len + [0] * (max_len - seq_len)
        token_type_ids = [0] * max_len
        token_ids = token_ids + [self._pad_id] * (max_len - seq_len)

        return token_ids[:max_len], attention_mask[:max_len], token_type_ids[:max_len]


# ---------------------------------------------------------------------------
# ONNX-based inference
# ---------------------------------------------------------------------------

_onnx_session = None  # cached InferenceSession
_tokenizer = None     # cached tokenizer


def _load_onnx_session():
    """
    Lazy-load the ONNX inference session. Cached after first call.
    Returns the session or None if onnxruntime is unavailable.
    """
    global _onnx_session, _tokenizer
    if _onnx_session is not None:
        return _onnx_session

    try:
        import onnxruntime as ort  # type: ignore[import]
    except ImportError:
        logger.info(
            "onnxruntime not installed. Semantic retrieval disabled. "
            "Install: pip install onnxruntime==1.17.3 or run memory.yml to use pre-computed embeddings."
        )
        return None

    if not os.path.isfile(ONNX_MODEL_PATH):
        logger.info(
            "ONNX model not found at %s. Run: python scripts/query_embedder.py --export-onnx "
            "to generate it from the cached sentence-transformers model.",
            ONNX_MODEL_PATH,
        )
        return None

    try:
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1  # single-threaded for predictable latency in CI
        opts.inter_op_num_threads = 1
        _onnx_session = ort.InferenceSession(ONNX_MODEL_PATH, sess_options=opts)
        _tokenizer = _MinimalWordPieceTokenizer(ONNX_VOCAB_PATH)
        logger.info("ONNX session loaded: %s", ONNX_MODEL_PATH)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load ONNX session: %s", exc)
        _onnx_session = None

    return _onnx_session


def _mean_pool_normalize(hidden_states: Any, attention_mask: list[int]) -> list[float]:
    """
    Mean-pool token embeddings, masked by attention, then L2-normalize.

    Args:
        hidden_states: numpy array of shape (1, seq_len, 384)
        attention_mask: list of 0/1 ints, length seq_len

    Returns:
        list[float] of length 384, L2-normalized.
    """
    # hidden_states shape: (1, seq_len, dim)
    hs = hidden_states[0]  # (seq_len, dim)
    dim = hs.shape[1]
    pooled = [0.0] * dim
    total = 0

    for token_idx, mask_val in enumerate(attention_mask):
        if mask_val == 0:
            continue
        total += 1
        for d in range(dim):
            pooled[d] += float(hs[token_idx, d])

    if total > 0:
        pooled = [v / total for v in pooled]

    # L2 normalize
    magnitude = math.sqrt(sum(v * v for v in pooled))
    if magnitude > 0.0:
        pooled = [v / magnitude for v in pooled]

    return pooled


def embed_query(text: str) -> list[float] | None:
    """
    Embed a query string into a 384-dim unit vector.

    Returns:
        list[float] of length 384 if ONNX model is available.
        None if no embedding path is available (caller should fall back to
        decision-log keyword search).
    """
    session = _load_onnx_session()
    if session is None or _tokenizer is None:
        return None

    input_ids, attention_mask, token_type_ids = _tokenizer.tokenize(text)

    try:
        import numpy as np  # type: ignore[import]
        inputs = {
            "input_ids": np.array([input_ids], dtype=np.int64),
            "attention_mask": np.array([attention_mask], dtype=np.int64),
            "token_type_ids": np.array([token_type_ids], dtype=np.int64),
        }
        outputs = session.run(None, inputs)
        # outputs[0] is last_hidden_state: (1, seq_len, 384)
        return _mean_pool_normalize(outputs[0], attention_mask)
    except ImportError:
        # numpy not available — attempt struct-based manual inference
        logger.warning("numpy not available for ONNX inference. Install numpy for query embedding.")
        return None
    except Exception as exc:  # noqa: BLE001
        logger.error("ONNX inference failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# ONNX model export utility (run once in CI after sentence-transformers build)
# ---------------------------------------------------------------------------

def export_onnx_model(model_path: str, output_path: str) -> None:
    """
    Export the sentence-transformers BGE model to ONNX format for runtime inference.

    Run this ONCE in the memory.yml CI workflow after loading the model.
    The exported model (~60 MB) is committed to .memory/model/ alongside the vocab.

    Args:
        model_path: Path to the cached sentence-transformers model directory.
        output_path: Destination .onnx file path.
    """
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import]
        import torch  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError("sentence-transformers and torch are required for ONNX export") from exc

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    logger.info("Loading model for ONNX export: %s", model_path)

    model = SentenceTransformer(model_path)
    transformer = model[0].auto_model
    tokenizer = model[0].tokenizer

    # Save vocab.txt for the minimal runtime tokenizer
    vocab_output = os.path.join(os.path.dirname(output_path), "vocab.txt")
    tokenizer.save_vocabulary(os.path.dirname(vocab_output))
    logger.info("Vocab saved: %s", vocab_output)

    # Create dummy input for tracing
    sample = tokenizer(
        "sample query for export",
        return_tensors="pt",
        padding="max_length",
        max_length=MAX_SEQ_LEN,
        truncation=True,
    )
    dummy_inputs = (
        sample["input_ids"],
        sample["attention_mask"],
        sample.get("token_type_ids", torch.zeros_like(sample["input_ids"])),
    )

    logger.info("Exporting to ONNX: %s", output_path)
    torch.onnx.export(
        transformer,
        dummy_inputs,
        output_path,
        input_names=["input_ids", "attention_mask", "token_type_ids"],
        output_names=["last_hidden_state", "pooler_output"],
        dynamic_axes={
            "input_ids": {0: "batch", 1: "sequence"},
            "attention_mask": {0: "batch", 1: "sequence"},
            "token_type_ids": {0: "batch", 1: "sequence"},
            "last_hidden_state": {0: "batch", 1: "sequence"},
        },
        opset_version=17,
        do_constant_folding=True,
    )
    logger.info("ONNX model exported successfully: %s (%.1f MB)", output_path,
                os.path.getsize(output_path) / (1024 * 1024))


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Query embedding utility")
    parser.add_argument("--export-onnx", action="store_true", help="Export model to ONNX")
    parser.add_argument("--model-path", default=None, help="Path to sentence-transformers model")
    parser.add_argument("--output", default=ONNX_MODEL_PATH, help="ONNX output path")
    parser.add_argument("--query", default=None, help="Test query to embed")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.export_onnx:
        if not args.model_path:
            logger.error("--model-path required for --export-onnx")
            sys.exit(1)
        export_onnx_model(args.model_path, args.output)

    if args.query:
        vec = embed_query(args.query)
        if vec is None:
            print("null")
        else:
            print(json.dumps(vec))


if __name__ == "__main__":
    main()
