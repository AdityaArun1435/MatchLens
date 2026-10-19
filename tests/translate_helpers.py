"""A fake model for the translation tests: it answers name, recap, explanation, translation and back-translation prompts.

Its "Hindi" and "Tamil" are mechanical: every English name becomes a made-up name in the right script, every other English
word becomes one filler word, digits and punctuation stay. That is enough to exercise every check without a real model.
"""
import re

FILLER = {"hi": "शब्द", "ta": "சொல்"}
_HI = "कखगघचजटडतनपबमयरलवसह"
_TA = "கசடதபமயரலவ"
_WORD = re.compile(r"[A-Za-z][A-Za-z'’\-]*")


def native(name: str, lang: str) -> str:
    """A deterministic made-up spelling of `name` in the language's script, word for word."""
    letters = _HI if lang == "hi" else _TA
    suffix = "ाम" if lang == "hi" else "ாம்"  # keeps one-letter team names from being a substring of everything
    words = ["".join(letters[ord(c) % len(letters)] for c in w if c.isalpha()) for w in name.split()]
    return " ".join(w + suffix if len(w) < 3 else w for w in words)


def fake_translation(source: str, lang: str, names: list[str]) -> str:
    text = source
    forms: list[tuple[str, str]] = []
    for name in names:
        forms.append((name, native(name, lang)))
        if " " in name:
            forms.append((name.split()[-1], native(name, lang).split()[-1]))
    for i, (eng, nat) in enumerate(sorted(forms, key=lambda f: -len(f[0]))):
        text = re.sub(rf"(?<![^\W\d_]){re.escape(eng)}(?:['’]s)?(?![^\W\d_])", f"\x00{i}\x00", text)
        text = text.replace(f"\x00{i}\x00", nat)
    text = re.sub(r"\btwice\b", "2", text)  # the real prompt asks for digits instead of number words
    return _WORD.sub(lambda m: m.group() if m.group() == "xG" else FILLER[lang], text)


def _after(user: str, marker: str) -> str:
    return user.split(marker)[-1].strip()


def router(lang: str, names: list[str], english: dict | None = None, explanation: dict | None = None, *, override=None, names_override=None):
    """Returns a callable for FakeProvider. `override(source, attempt)` may return a translation string to use instead."""
    seen: dict[str, int] = {}

    def route(system: str, user: str, schema: dict) -> dict:
        props = schema["properties"]
        if "names" in props:
            wanted = re.findall(r"^- (.+)$", user.split("Names:")[-1], re.M)
            answer = {n: native(n, lang) for n in wanted}
            if names_override:
                answer = names_override(answer)
            return {"names": [{"english": k, "native": v} for k, v in answer.items()]}
        if "translation" in props:
            if "literal translator" in system:
                return {"translation": "BACK: " + _after(user, "TEXT:")}
            source = re.split(r"ENGLISH (?:TITLE|PARAGRAPH|TEXT):\n", user)[-1].split("\n\nYour previous translation")[0].strip()
            seen[source] = seen.get(source, 0) + 1
            if override and (custom := override(source, seen[source])) is not None:
                return {"translation": custom}
            return {"translation": fake_translation(source, lang, names)}
        if "paragraphs" in props:
            return english
        if "why_it_mattered" in props:
            return explanation
        raise AssertionError(f"unexpected schema {list(props)}")

    return route
