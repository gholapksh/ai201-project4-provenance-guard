import re

def calculate_stylometrics(text: str) -> dict:
    """
    Returns a dict with sentence_length_variance, type_token_ratio, and
    structural_score (0.0-1.0), where higher = more human-like.

    Rationale: AI-generated text tends toward uniform sentence length and
    repeated vocabulary. Human writing tends to vary more in both. So higher
    variance + higher type-token ratio (TTR) is scored as more human-like.
    """
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
    words = [w.strip(",().\"\";:").lower() for w in text.split() if w.strip()]

    if not words or not sentences:
        return {"sentence_length_variance": 0.0, "type_token_ratio": 0.0, "structural_score": 0.5}

    sentence_lengths = [len(s.split()) for s in sentences]
    avg_length = sum(sentence_lengths) / len(sentence_lengths)

    if len(sentence_lengths) > 1:
        variance = sum((x - avg_length) ** 2 for x in sentence_lengths) / (len(sentence_lengths) - 1)
    else:
        variance = 0.0

    ttr = len(set(words)) / len(words)

    # Normalize variance into 0-1 range (50 chosen as a practical ceiling for
    # sentence-length variance in typical prose; values above are clamped).
    structural_score = (min(variance / 50.0, 1.0) * 0.4) + (ttr * 0.6)

    return {
        "sentence_length_variance": round(variance, 2),
        "type_token_ratio": round(ttr, 2),
        "structural_score": round(structural_score, 2),
    }