"""A canned provider for browser tests (MATCHLENS_LLM_PROVIDER=fake). Never used for real output.

It answers recap and explain prompts with fixed text that passes the real validators for the 2022 World Cup final, so an
end-to-end test exercises the whole pipeline (context, validation report, cache, shootout paragraph) without Ollama.
Translation prompts get the English source back, which the translation checks reject, so Hindi and Tamil requests show
the English-fallback path.
"""
import re

NAME = "e2e-fake"

RECAP = {
    "title": "Argentina 3-3 France",
    "paragraphs": [
        {
            "text": "Argentina 3-3 France after extra time. Total xG was Argentina 2.76, France 2.27. Shots were Argentina 20, France 10.",
            "cites": ["m_008"],
        },
        {
            "text": "Argentina took the lead after Lionel Messi scored a penalty in regular time at 23'. The score was Argentina 1-0 France.",
            "cites": ["m_001"],
        },
        {
            "text": "Ángel Di María extended the lead at 36'. The score was Argentina 2-0 France.",
            "cites": ["m_002"],
        },
        {
            "text": "France reduced the deficit after Kylian Mbappé scored a penalty in regular time at 80'. Mbappé levelled the score at 81'. The score was Argentina 2-2 France.",
            "cites": ["m_003", "m_004"],
        },
        {
            "text": "Argentina regained the lead at 108' when Lionel Messi scored in open play. France equalised at 118' with a penalty in extra time.",
            "cites": ["m_006", "m_008"],
        },
    ],
}


class E2EProvider:
    name = NAME

    def is_available(self) -> bool:
        return True

    def generate_json(self, system: str, user: str, json_schema: dict) -> dict:
        props = json_schema["properties"]
        if "paragraphs" in props:
            return RECAP
        if "why_it_mattered" in props:
            moment_id = props["moment_id"]["enum"][0]
            return {
                "moment_id": moment_id,
                "why_it_mattered": "This moment changed the score and is marked as the target moment in the data.",
                "context": "It sits between the moments listed before and after it in the data.",
                "cites": [moment_id],
            }
        if "translation" in props:
            source = re.split(r"ENGLISH (?:TITLE|PARAGRAPH|TEXT):\n", user)[-1].strip()
            return {"translation": source}
        return {"names": []}
