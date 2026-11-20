"""The machine-readable mark on text the model wrote (EU AI Act, Article 50(2); ADR 0024).

Only the words on the output records and the page carry it. Nothing the model reads changes.
"""

from collections.abc import Iterable
from typing import Final

from app.api.schemas import CamelModel

GENERATOR: Final = "Open Door AI assistant"
# IPTC's term for content created by a trained algorithm (a generative model).
DIGITAL_SOURCE_TYPE: Final = (
    "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"
)


class AiGeneratedOut(CamelModel):
    """The machine-readable mark on text the model wrote (Article 50(2); ADR 0024)."""

    generator: str
    # The models that wrote it, each once, in the order they served.
    models: list[str]
    # The IPTC digital source type for content made by a generative model.
    digital_source_type: str


def ai_generated_out(models: Iterable[str]) -> AiGeneratedOut:
    """The mark for text the given models wrote, each model once, in the order given."""
    return AiGeneratedOut(
        generator=GENERATOR,
        models=list(dict.fromkeys(models)),
        digital_source_type=DIGITAL_SOURCE_TYPE,
    )
