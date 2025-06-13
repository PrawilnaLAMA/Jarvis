from difflib import SequenceMatcher

def is_similar(word, target, threshold=0.7):
    return SequenceMatcher(None, word, target).ratio() >= threshold
