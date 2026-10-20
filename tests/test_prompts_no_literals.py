"""Prompt files must not carry literal scores, minutes or names: the model copies them into other matches."""
import re

from matchlens import config
from matchlens.recap import prompts

LITERALS = re.compile(r"\b\d+-\d+\b|\b\d+\+\d+|\b\d+'|\b\d+(st|nd|rd|th) minute|Argentina|France|Messi|Mbapp|Netherlands", re.I)
NAME_FILES = {"names_system.md", "names_task.md"}


def test_no_literal_scores_minutes_or_names():
    for path in config.PROMPTS_DIR.glob("*.md"):
        if path.name in NAME_FILES:
            continue
        hit = LITERALS.search(path.read_text(encoding="utf-8").replace("0-9", ""))  # "0-9" is the digit range
        assert hit is None, f"{path.name} contains the literal {hit.group(0)!r}; use a {{{{placeholder}}}}"


class _Fake:
    class meta:
        home_team, away_team = "Home FC", "Away FC"

    class summary:
        final_score, went_to_extra_time = (2, 2), True


def test_placeholders_are_filled():
    for name in ("system_base", "recap_task", "audience_analyst", "audience_broadcaster", "audience_fan"):
        text = prompts.load_filled(name, _Fake)
        for key in ("home", "away", "final_score", "result_phrase", "title_form"):
            assert "{{" + key + "}}" not in text
    assert "the match ended 2-2 after extra time" in prompts.load_filled("system_base", _Fake)
