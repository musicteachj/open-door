"""The content hash that names a handbook version's contents."""

import hashlib
import json
import struct
from collections.abc import Sequence

from app.domain.handbook.blocks import blocks_to_json
from app.domain.handbook.chunks import CHUNKER_VERSION, chunks_for
from app.domain.handbook.models import Handbook


def vectors_digest(vectors: Sequence[Sequence[float]]) -> str:
    """A SHA-256 over the vectors in order, each as its length and its little-endian float32s."""
    digest = hashlib.sha256()
    for vector in vectors:
        digest.update(struct.pack(f"<I{len(vector)}f", len(vector), *vector))
    return digest.hexdigest()


def derived_digest(handbook: Handbook) -> str:
    """A SHA-256 over what the parser and chunker make of the sources, in the handbook's order:
    each section's key and its blocks as stored, then each chunk's section, position, heading,
    passage IDs, and text. A code change that renumbers passages or alters the stored blocks
    changes it, even when no source file and no CHUNKER_VERSION did."""
    derived = [
        {
            "section": section.id,
            "blocks": blocks_to_json(section.blocks),
            "chunks": [
                [
                    chunk.section_id,
                    chunk.position,
                    chunk.heading,
                    list(chunk.passage_ids),
                    chunk.text,
                ]
                for chunk in chunks_for(section)
            ],
        }
        for section in handbook.sections
    ]
    encoded = json.dumps(derived, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def content_hash(
    handbook: Handbook, *, model: str, dimensions: int, vectors: Sequence[Sequence[float]]
) -> str:
    """A SHA-256 over every source file (path and text, in path order), the chunker's version,
    the embedding model and dimensions, a digest of the blocks and chunks derived from the
    sources, and a digest of the chunks' vectors in order. Anything that would change the stored
    blocks, chunks, or vectors changes the hash, so it names a new version: an edit to only the
    committed embedding cache needs a new label, which a reviewer can see."""
    files = sorted((file.path, file.text) for file in handbook.files)
    payload = {
        "files": files,
        "chunkerVersion": CHUNKER_VERSION,
        "model": model,
        "dimensions": dimensions,
        "derivedDigest": derived_digest(handbook),
        "vectorsDigest": vectors_digest(vectors),
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
