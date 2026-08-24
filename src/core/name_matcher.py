"""Linear-time multi-pattern matching for authority names in scripture text."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable


def count_keywords(text: str, keywords: Iterable[str]) -> dict[str, int]:
    """Count many literal keywords in one pass using an Aho-Corasick automaton.

    Counts use the same non-overlapping rule as ``str.count`` for each keyword.
    Duplicate and empty keywords are ignored.
    """
    unique_keywords = list(dict.fromkeys(word for word in keywords if word))
    if not text or not unique_keywords:
        return {}

    transitions: list[dict[str, int]] = [{}]
    failures = [0]
    outputs: list[list[str]] = [[]]

    for word in unique_keywords:
        state = 0
        for char in word:
            next_state = transitions[state].get(char)
            if next_state is None:
                next_state = len(transitions)
                transitions[state][char] = next_state
                transitions.append({})
                failures.append(0)
                outputs.append([])
            state = next_state
        outputs[state].append(word)

    queue = deque(transitions[0].values())
    while queue:
        state = queue.popleft()
        for char, next_state in transitions[state].items():
            queue.append(next_state)
            fallback = failures[state]
            while fallback and char not in transitions[fallback]:
                fallback = failures[fallback]
            failures[next_state] = transitions[fallback].get(char, 0)
            outputs[next_state].extend(outputs[failures[next_state]])

    counts: dict[str, int] = {}
    last_end: dict[str, int] = {}
    state = 0
    for index, char in enumerate(text):
        while state and char not in transitions[state]:
            state = failures[state]
        state = transitions[state].get(char, 0)
        for word in outputs[state]:
            start = index - len(word) + 1
            if start >= last_end.get(word, 0):
                counts[word] = counts.get(word, 0) + 1
                last_end[word] = index + 1

    return counts
