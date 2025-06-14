from difflib import SequenceMatcher
import re

def is_similar(word, target, threshold=0.7):
    return SequenceMatcher(None, word, target).ratio() >= threshold

# Define command patterns using regex
COMMAND_PATTERNS = {
    "google": r"\bgoogle\b",
    "youtube": r"\byoutube\b",
    "time": r"\btime\b",
    "discord_message": r"\bdiscord_message\b",
}

def parse_command(message):
    for command, pattern in COMMAND_PATTERNS.items():
        if re.search(pattern, message.lower()):
            return command
    return None
