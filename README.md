# MatchLens

Local-only football match intelligence.

* **Phase 1** (data layer): loads StatsBomb open data, normalises the events, detects
the key moments of a match with plain Python, and serves everything through a small FastAPI app. No LLM in this phase, no ML.
* **Phase 2** (section below): grounded recaps and moment explanations written by a local LLM through Ollama,
  checked by the backend before anything is shown. No paid APIs, no keys in either phase.

Default match: **2022 FIFA World Cup final, Argentina v France** (3-3 after extra time, Argentina won 4-2 on penalties).
Two more are preloaded: **France 4-3 Argentina** (2018 round of 16, seven goals) and **Netherlands 2-2 Argentina**
(2022 quarter-final, 90+11' equaliser, extra time, shootout, 16 card events). Match ids are resolved from StatsBomb's
`matches.json` by team and stage, never hard-coded.

## Setup (Windows 11, PowerShell, Python 3.11+)

```powershell
git clone <this repo>; cd MatchLens
py -3.11 -m venv .venv            # or: python -m venv .venv
.\.venv\Scripts\Activate.ps1      # if blocked: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
python scripts/fetch_data.py      # one-off download into data/raw/ (about 11 MB), then everything runs offline
```

`data/raw/` is not in git. StatsBomb's data agreement (`LICENSE.pdf` in their repo, clause 1.2.1) forbids
distributing or reproducing the data to third parties, so each user fetches it themselves. Tests that need the data
are skipped (not failed) until you have run `fetch_data.py`.

Add any other match: `python scripts/fetch_data.py --add MATCH_ID:COMPETITION_ID:SEASON_ID`.

## Run

```powershell
python scripts/inspect_match.py                      # moments table for the final
python scripts/inspect_match.py --all --stats        # all preloaded matches, with each moment's numbers
python scripts/inspect_match.py --match-id 7580 --min-importance 0.5

uvicorn matchlens.api:app --reload                   # http://127.0.0.1:8000/docs
python -m pytest                                     # all offline
```

### API

| Endpoint | Returns |
|---|---|
| `GET /matches` | preloaded matches: metadata, extra time flag, shootout winner, moment count |
| `GET /matches/{id}/summary` | `MatchSummary`: scores (90 min, extra time, final), shootout, xG, shots, possession, per-minute xG timeline |
| `GET /matches/{id}/moments?min_importance=` | moments in match order |
| `GET /matches/{id}/events?from_minute=&to_minute=&period=` | normalised events in match order (for live replay) |

Each match is loaded and processed once and kept in memory. `minute` is the StatsBomb elapsed minute and repeats
across a period boundary (stoppage time of the first half overlaps the start of the second), so pass `period`
when you need to be exact. Order by `index`, not by minute.

## Layout

```
matchlens/config.py        every threshold and default
matchlens/loader.py        download + cache of raw JSON in data/raw
matchlens/normalise.py     raw event -> Event (clock labels, shootout handling)
matchlens/importance.py    importance scoring, one place to tune
matchlens/detect/          one module per moment type, MatchContext holds the goal log
matchlens/summary.py       MatchSummary
matchlens/service.py       per-match cache used by the API and scripts
matchlens/llm/             provider interface, Ollama client, FakeProvider (Phase 2)
matchlens/recap/           context builder, validators, rules, pipeline, fallback, cache (Phase 2); translate, names_i18n (Phase 3)
data/names/                Hindi and Tamil name maps (committed, edit by hand)
prompts/                   prompt files (Phase 2); editing one invalidates cached outputs
docs/data_notes.md         the real StatsBomb fields this code relies on
```

## Moment definitions

### Player names

Each event keeps the full StatsBomb name (`player`), the StatsBomb id (`player_id`) and adds `player_display_name`:
`DISPLAY_NAME_OVERRIDES` in `config.py` (keyed by id or full name) first, then the lineup `player_nickname`, then the
full name. Moments carry parallel `players` (full names), `player_ids` and `player_display_names`. Headlines and the
names inside `stats` use display names.

### Moment fields

Every moment has an `id` (`m_001`, in match order), `minute`, `clock_label` (`23'`, `45+2'`, `90+3'`, `Pens`),
`period`, `type`, `team`, `players`, `score_before` / `score_after` (home, away; in-play goals only),
`importance` (0 to 1), a one-line `headline`, the `stats` behind it and `evidence` (event ids, all present in
`/events`). Headlines state numbers and never claim a cause.

* **goal**: any in-play goal, including penalties and own goals (credited to the team that benefits). Stats hold
  the goal kind, assist, xG, whether it took the lead or equalised, any earlier shot in the same possession (rebounds)
  and the completed passes of the scoring team in that possession before the shot.
* **big_chance_missed**: an in-play shot with xG at or above `BIG_CHANCE_XG` (0.25) that did not score.
* **red_card** / **second_yellow**: straight reds and second yellows. Plain yellows are not moments.
* **momentum_swing**: every minute, compare the two teams' xG over the previous 10 minutes. The window leader is the
  team ahead by at least `MOMENTUM_MIN_LEAD_XG` (0.15); otherwise nobody leads. A swing is logged when a different team
  becomes leader and stays leader for at least `MOMENTUM_HOLD_MIN` (5) minutes. Windows are cut at the start of each
  period and state is reset, so nothing spans half-time or the break before extra time. Both teams' xG and shots are in `stats`.
* **substitution_impact**: for a team's substitution (same-team changes within 2 minutes count as one), compare that
  team's xG and shots in the window before and after, inside the same period. Flagged when xG moves by at least 0.4 or
  shots by at least 3 per 10 minutes, up or down. Windows shrink to fit the period; changes without 5 minutes on both
  sides in the period are skipped. Opponent numbers are included for context.
* **quick_response**: goals bunched together, measured in play time (half-time and the break before extra time do
  not count). Either 2+ goals by one team within `QUICK_RESPONSE_BRACE_MIN` (5) minutes, or a goal that equalises or
  takes the lead within `QUICK_RESPONSE_REPLY_MIN` (3) minutes of that team conceding. Overlapping triggers merge into
  one moment, `stats.reasons` lists which fired, and `evidence` holds only the goal events.
* **penalty_shootout**: one moment with every kick in order, the tally and the winner.

Penalties awarded in play are excluded from the momentum and substitution windows (`EXCLUDE_PENALTIES_FROM_WINDOWS`),
because a 0.78 xG penalty reflects a referee decision rather than a spell of play. They still count as goals and
in all match totals. Shootout kicks never count towards score, xG or shot totals.

### Importance

`matchlens/importance.py` documents and holds all weights. In short: goals 0.60, +0.30 if the goal takes the lead or
equalises, +0.10 if late or in extra time; big chances 0.25 + 0.5 x xG (+0.10 when the score is within a goal); red
card 0.70, second yellow 0.65; quick response 0.80 (+0.10 if it takes the lead or equalises, +0.05 if late); shootout 0.95; momentum swings 0.25 to 0.55 by xG lead; substitutions 0.15 to 0.40 by xG change.

## Phase 2: grounded recaps and explanations (local LLM)

The model never sees raw events. It sees one match's `MatchSummary` and `Moment` list rendered as compact text
(`matchlens/recap/context.py`), writes paragraphs that cite moment ids, and the backend checks every paragraph.

### Ollama setup on Windows

```powershell
winget install Ollama.Ollama          # or download from https://ollama.com
ollama --version
ollama pull qwen3:8b                  # about 5 GB, fits in 8 GB of VRAM with room for the context
ollama run qwen3:8b "Say hello"       # quick test; the Ollama app/service listens on http://localhost:11434
```

Pick a model by editing `OLLAMA_MODEL` in `matchlens/config.py` or setting `MATCHLENS_OLLAMA_MODEL` for one session:

```powershell
$env:MATCHLENS_OLLAMA_MODEL = "gemma3:12b"
```

Any instruct model that supports structured output works. On an 8 GB GPU stay at roughly 8B parameters with a
4-bit build. Models with a thinking mode are run with thinking disabled (`OLLAMA_DISABLE_THINKING`); the client
retries without the flag for models that do not support it. Cached outputs are keyed by model name, so switching
models never serves another model's text.

### Generate

```powershell
python scripts/generate_recap.py --audience all                       # analyst, broadcaster, fan for the default match
python scripts/generate_recap.py --match 7580 --audience fan --length short
python scripts/generate_recap.py --explain m_005 --audience broadcaster
python scripts/generate_recap.py --template                           # deterministic baseline, no LLM
python scripts/generate_recap.py --audience all --out recaps.md       # also save to a file
```

Output shows each paragraph followed by its `[m_00x]` citations, the validation report and timings.
If Ollama is not running the script exits with a message saying how to start it.

### API

| Endpoint | Returns |
|---|---|
| `POST /matches/{id}/recap` body `{"audience": "analyst", "length": "medium", "language": "en", "refresh": false}` | recap, validation report, model name, generation time, `cached` |
| `GET /matches/{id}/moments/{moment_id}/explain?audience=&language=` | `why_it_mattered`, `context`, `cites`, validation report |

`audience` is `analyst`, `broadcaster` or `fan`; `length` is `short` or `medium`; `language` is `en`, `hi` or `ta`
(see Phase 3 below).
A server that is not running gives HTTP 503 with a hint; `/docs` has the schemas.

### How validation works

Each paragraph (and for explanations each text field) must pass all of these:

1. **Citations.** At least one moment id; every id must exist and must have been part of the data given to the model.
   The JSON schema sent to Ollama lists the valid ids as an enum, and the backend checks again.
2. **Numbers.** Every number in the text must appear in the match summary or in the cited moments, as shown to the model.
   Scores (`2-2`, either order), stoppage minutes (`90+3'`), decimals (xG), integers and counted number words ("two goals",
   "twice") are separate kinds. A minute from an uncited moment fails.
3. **Names.** A mention of a player who is not named in the cited moments fails (full name, display name, surname or given
   name, ignoring accents and case). Capitalised words that are not teams, roster players or common sentence openers
   (`NAME_CHECK_SENTENCE_STARTERS` in `config.py`) are treated as invented names. The title may not name players at all.

4. **Score-state verbs.** "took the lead", "went ahead", "equalised", "levelled", "won" and "drew" are checked against the
   score before and after the cited goal moments (and the goals behind a cited quick-response moment). A named minute narrows
   the check to the goal at that minute; a named team must be the side that scored. "Won" and "drew" are checked against the
   final score, the score after 90 minutes and the shootout winner.
5. **Shootout claims.** The model sees the kicks as a numbered list (kick, team, taker, result). A sentence in a paragraph that
   cites the shootout is checked for ordinals ("first penalty", "opening kick", "France's third penalty") and for a named
   taker scoring, missing or being saved. Rules are in `matchlens/recap/rules.py`.
6. **Banned phrases.** `BANNED_PHRASES` in `config.py` (title, trophy, champions, history, hosts, favourites, stadium, crowd,
   record, ...) fails for every audience. The competition and stage text from the data is exempt.
7. **Opinion words.** `OPINION_WORDS` in `config.py` (dramatic, well-taken, stunning, ...) fails for the analyst and the
   broadcaster and is allowed for the fan (`OPINION_ALLOWED_AUDIENCES`).

If anything fails, the model is called once more with the exact errors listed. The attempt with more valid paragraphs
wins; invalid paragraphs are dropped; if none survives, the deterministic template recap is used
(`matchlens/recap/fallback.py`, also the baseline to compare the model against). A model server that is not running is
reported as an error, never papered over with the template. The `report` in every response says what was retried,
dropped or replaced. Only model-written results are cached, in `data/generated/` (gitignored), keyed by match, audience,
length, language, model and a hash of the files in `prompts/`; editing a prompt invalidates the cache.

What validation cannot see: claims that use no numbers or names (who dominated, why something happened), correct numbers
attached to the wrong thing (a real minute given to the wrong goal when both moments are cited), outside knowledge
phrased without names or numbers, tone beyond the opinion-word list, wrong claims that avoid every listed verb or name, and misspelt names that are not close to
any roster name. Prompts forbid all of these, but nothing enforces it.

### Tests

`python -m pytest` runs everything offline. The Ollama client is tested with a mock HTTP transport, the pipeline with a
`FakeProvider`. `tests/test_ollama_integration.py` and `tests/test_ollama_translation.py` are marked `needs_ollama` and
are skipped unless a server with the configured model is reachable.

## Phase 3: Hindi and Tamil

Nothing is generated directly in Hindi or Tamil. The English recap or explanation is generated and validated first (all
of Phase 2), then each paragraph is translated on its own and checked again.

```powershell
python scripts/generate_recap.py --language hi --back-translate
python scripts/generate_recap.py --audience all --language all --back-translate --out recaps_all.md
```

`--language en|hi|ta|all`. `--back-translate` asks the model to translate every Hindi or Tamil paragraph back to English and
prints it under the paragraph, so a person can judge meaning drift. It is never used to accept or reject a translation.
Over HTTP, `{"language": "hi"}` on the recap endpoint and `?language=ta` on the explain endpoint. The result carries
`source_recap` (the validated English), each paragraph's `language` and `note`, and `report.translation`.

### What is checked on each translated paragraph

1. **Numbers.** The translation must contain exactly the English numbers, as Western digits (any Devanagari or Tamil digit
   is converted to 0-9 first, and the report notes it). That covers scores, minutes (`90+3'`), xG and counts. Number words in
   the English ("two goals", "twice") are shown to the model as digits; a digit for a spelt-out number or ordinal ("second"
   -> 2) is not counted as invented.
2. **Names.** Every player and team named in the English must appear as spelt in `data/names/{lang}.json`. A name written in
   several words in the English ("Di María") may not shrink to one word. Names in Latin letters, names that are not in the
   English, and text not mostly in the right script all fail.
3. **Wording.** The Hindi and Tamil banned-phrase and opinion-word lists in `config.py` (substring match, so inflected
   forms are caught).
4. **Citations** are copied from the English paragraph, never regenerated.

One retry with the exact errors. If it still fails, that paragraph is shown in English with a note in the target
language and in English; nothing is dropped, and the report lists what failed. Results that contain such a paragraph are not
cached, so the next request tries again.

### Name maps and review

`data/names/hi.json` and `data/names/ta.json` map each English display name (and the two team names) to its spelling in
Hindi or Tamil script. Missing names are written by the model once; existing entries are never overwritten. **These files
are first drafts, not reviewed: correct them by hand and set `"reviewed": true`.** Editing a map invalidates cached
translations. The Hindi and Tamil banned and opinion lists in `config.py` (`BANNED_PHRASES`, `OPINION_WORDS`,
`BANNED_PHRASE_EXEMPT`) are also first drafts marked for review.

### Written shootout paragraph, glossary and quality

- **Shootout paragraph.** The model never sees the shootout. A paragraph per audience is written from the kick list
  (`matchlens/recap/shootout.py`), cites only the shootout moment, and is translated like any other paragraph.
- **Banned and opinion lists are in the prompt**, as well as being checked afterwards (`rules.wording_instructions`).
- **In-play penalties versus shootout kicks.** The data says "penalty in regular time" or "penalty in extra time"; a bare
  "penalty" or "penalty spot" in play is rejected, and a shootout kick is always "in the shootout".
- **Repetition and score lines.** A sentence repeated from an earlier paragraph, or a score line such as "France 2-2 France"
  or one the cited moments do not show, is rejected.
- **Football glossary** (`data/glossary/hi.json`, `ta.json`): 20 terms with a fixed translation (`use`) and accepted stems
  (`accept`). When the English source uses a term (patterns in `matchlens/recap/glossary.py`), the translation must contain
  one of its forms, and the translate prompt lists the fixed forms. First drafts, please review.
- **Quality.** `config.LANGUAGE_QUALITY` says `en` stable, `hi` machine-translated, `ta` experimental. Every recap and
  explain response has a `quality` field.

### What this does not catch

A translation can keep every number and name and still change the meaning (a verb, who did what, "regained" read as
"maintained"). Use `--back-translate` and a Hindi or Tamil reader to judge it. Tamil in particular should be labelled
experimental until someone has reviewed it.

## Attribution

Data: **StatsBomb Open Data**, https://github.com/statsbomb/open-data. Used under the StatsBomb Public Data User
Agreement. If you publish or share analysis built on this data, state StatsBomb as the source and use their logo
(see their media pack: https://statsbomb.com/media-pack/). StatsBomb provides the data as is, and this project is
not affiliated with or endorsed by StatsBomb.
