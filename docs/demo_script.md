# 90-second demo script

Screen recording of the web app at 1360x900, dark theme, mouse visible. Start with `.\start.ps1` and Ollama running.
The 2022 final recaps (English and Tamil, analyst, medium) must already be cached: `python scripts/warm_cache.py --match 3869685 --min-importance 0.7`.
Each shot has a click path and one line of voiceover. Total length is about 90 seconds.

| # | Time | Screen | Do | Voiceover |
|---|---|---|---|---|
| 1 | 0:00 to 0:05 | Match picker | Open `http://localhost:3000`. Click **Argentina v France, 2022 final**. | "This is the 2022 World Cup final, and everything you will see runs on this laptop with no internet." |
| 2 | 0:05 to 0:25 | Match page, **Watch live** | Click **Watch live**. Set speed to **30x**. Drag the scrubber to the 79th minute. Let it play. | "I replay the match from the 79th minute. The score is hidden, the xG chart draws in as events arrive." |
| 3 | | Live view, 80' and 81' | Stay on the live view while the clock passes 80' and 81'. Point at the two goals, the caption, and the **quick response** moment popping into the list. | "Two France goals in under two minutes. The detector finds the moments as they happen, using only events up to the clock." |
| 4 | 0:25 to 0:30 | Live view, full time | Wait for full time, or click the scrubber to the end. Click **Read the recap**. | "At full time I can open the recap." |
| 5 | 0:30 to 0:45 | Recap panel, English | Keep audience **Analyst**, length **Medium**. Scroll slowly past the first paragraph (the result) and the 80' and 81' paragraph. | "A local 8 billion parameter model wrote this. It never saw raw data, only a list of detected moments." |
| 6 | 0:45 to 0:55 | Citations | Hover the citation chips under the 80' and 81' paragraph. Click the chip for the 81' goal: the page jumps to that moment and highlights it. The moment side panel opens. | "Every sentence cites the moment it is based on. Click a citation and you land on the evidence." |
| 7 | 0:55 to 1:10 | **How was this checked?** | Click **How was this checked?** Point at the chips (retries, dropped), the attempt list with its errors, and the model and time. | "A validator checks every sentence: numbers, names, who took the lead. A bad paragraph is retried once, then dropped, and the full report is shown here, nothing hidden." |
| 8 | 1:10 to 1:20 | Language switch | Click **TA** in the language toggle. The cached Tamil recap appears. Point at the **experimental** quality badge. | "The checked English is translated into Tamil, and the translation is checked again for numbers and names. Tamil is labelled experimental." |
| 9 | 1:20 to 1:30 | **Show English** | Click **Show English** on one paragraph, then the global toggle. | "Show English displays the checked source under any translated paragraph, so a reader can always compare." |

## Recording notes

- Do the live replay first and the recap second: the point is that the product reacts as the match unfolds, then explains it.
- If a paragraph in the recap was dropped, say so out loud while the report is open. Honesty about the checker is the selling point.
- Record in one take at normal speed, trim in editing. Do not speed up the recap panel.
- Keep the voiceover to the single lines above. Do not mention penalties, history or players' quality: the app does not either.
