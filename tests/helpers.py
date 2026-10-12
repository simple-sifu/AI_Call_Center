"""Helpers shared by test modules (the tests folder is on sys.path)."""

import re

# A quantifier with no upper bound (``*``, ``+`` or ``{n,}``) outside a character class.
UNBOUNDED = re.compile(r"(?<!\\)[*+](?![^\[]*\])|\{\d*,\}")

# Number words, kept by hand so the tests check the spoken-number table, not mirror it.
UNIT_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
ZERO_WORDS = ["zero", "oh", "o"]
TEEN_WORDS = [
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
TENS_WORDS = {
    "2": "twenty",
    "3": "thirty",
    "4": "forty",
    "5": "fifty",
    "6": "sixty",
    "7": "seventy",
    "8": "eighty",
    "9": "ninety",
}
# Every number word the spoken pass reads, so none of a value's words can hide.
DIGIT_WORDS = {
    *UNIT_WORDS,
    *ZERO_WORDS,
    *TEEN_WORDS,
    *TENS_WORDS.values(),
    "hundred",
    "double",
    "triple",
}


class FakeTranscriber:
    """Fake ASR that returns the given raw segments for any file."""

    def __init__(self, segments):
        self.segments = list(segments)

    def transcribe(self, path):
        return self.segments
