"""Compose readable Studio captions from source-timed words, without retiming speech."""
from math import inf


def _punctuation(text):
    return text.rstrip("\"')]}\u201d\u2019\u00bb")[-1:] or " "


def _compose_run(words):
    # Look ahead so a mechanical line-length split doesn't strand the last word.
    n = len(words)
    costs, stops = [inf] * n + [0.0], [0] * n
    for i in range(n - 1, -1, -1):
        length = 0
        for j in range(i, min(i + 36, n)):
            word = words[j]
            length += len(word["text"]) + (j > i and word.get("_space", True))
            duration = word["end"] - words[i]["start"]
            if j > i and (length > 76 or duration > 6):
                break
            # Prefer complete, moderately sized phrases over flashes or dense cards.
            cost = 4 + 12 * max(0, 1.25-duration)**2 + max(0, length-52)**2 / 100
            cost += max(0, length-22*max(duration, 1))**2 / 45
            if i == j and n > 1:
                cost += 12
            if j+1 < n:
                mark = _punctuation(word["text"])
                gap = max(0, words[j+1]["start"] - word["end"])
                cost += (0 if mark in ".!?\u2026\u3002\uff01\uff1f" else
                         1 if mark in ",;:\uff0c\uff1b" else 7) - min(6, gap*10)
            if cost + costs[j+1] < costs[i]:
                costs[i], stops[i] = cost + costs[j+1], j+1
            # A short interjection immediately followed by more speech can share
            # a card. Long pauses and identified speaker changes already split runs.
            if (_punctuation(word["text"]) in ".!?\u2026\u3002\uff01\uff1f"
                    and not (duration < .85 and length <= 14 and j+1 < n
                             and words[j+1]["start"]-word["end"] < .18)):
                break
    i = 0
    while i < n:
        stop = stops[i]
        text = words[i]["text"] + "".join((" " if w.get("_space", True) else "") + w["text"]
                                           for w in words[i+1:stop])
        yield {**words[i], "text": text, "end": words[stop-1]["end"]}
        i = stop


def compose_subtitles(words, end=None):
    result, run = [], []
    for word in words:
        existing = "existingIndex" in word
        if run and (existing or word.get("speaker") != run[-1].get("speaker")
                    or word.get("_limit") != run[-1].get("_limit")
                    or word["start"] - run[-1]["end"] >= .85):
            result.extend(_compose_run(run))
            run = []
        if existing:
            result.append(dict(word))
        else:
            run.append(word)
    result.extend(_compose_run(run))
    for i, cue in enumerate(result):
        limit = cue.pop("_limit", end)
        cue.pop("_space", None)
        if limit is None or "existingIndex" in cue:
            continue
        if i+1 < len(result):
            limit = min(limit, result[i+1]["start"])
        # Borrow only unused time AFTER the words; never anticipate the next line.
        wanted = cue["start"] + max(1.15, len(cue["text"])/19)
        cue["end"] = max(cue["end"], min(wanted, cue["end"]+1.1, limit))
    return result
