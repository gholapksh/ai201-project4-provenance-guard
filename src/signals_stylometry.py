import re

def calculate_stylometrics(text: str) -> dict:
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
    words = [w.strip(",().\"\";:").lower() for w in text.split() if w.strip()]
    if not words or not sentences:
        return {"variance": 0.0, "ttr": 0.0, "structural_score": 0.5}
    sentence_lengths = [len(s.split()) for s in sentences]
    avg_length = sum(sentence_lengths) / len(sentence_lengths)
    variance = sum((x - avg_length) ** 2 for x in sentence_lengths) / (len(sentence_lengths) - 1) if len(sentence_lengths) > 1 else 0.0
    ttr = len(unique_words := set(words)) / len(words)
    structural_score = (min(variance / 50.0, 1.0) * 0.4) + (ttr * 0.6)
    return {"sentence_length_variance": round(variance, 2), "type_token_ratio": round(ttr, 2), "structural_score": round(structural_score, 2)}
