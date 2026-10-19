"""Text helpers shared by the validators."""
import unicodedata


def fold(text: str) -> str:
    """Lower-case and remove accents, one output character per input character."""
    out = []
    for ch in text:
        base = "".join(c for c in unicodedata.normalize("NFD", ch) if not unicodedata.combining(c))
        out.append(base.lower() if len(base) == 1 else ch.lower())
    return "".join(out)
