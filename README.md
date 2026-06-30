# ai201-project4-provenance-guard
project 4
# Provenance Guard

A backend system that classifies submitted creative text as likely human-written or AI-generated, surfaces a plain-language transparency label, and lets creators appeal a classification they believe is wrong.

## Architecture Overview

A submission flows through the system as follows:

1. **POST /submit** receives `text` and `creator_id`, and first passes through **rate limiting** (Flask-Limiter). Requests over the limit return `429`.
2. The text is passed to two independent **detection signals**:
   - **Signal 1 (Groq LLM)** sends the text to `llama-3.3-70b-versatile` and asks it to return a 0.0–1.0 score (1.0 = confidently human, 0.0 = confidently AI).
   - **Signal 2 (stylometry)** computes sentence-length variance and type-token ratio in pure Python and combines them into a structural score on the same 0–1 scale.
3. Both scores are combined by the **Unified Calibration Engine** using a fixed weighted formula: `0.6 * llm_score + 0.4 * structural_score`.
4. The combined score is mapped to one of three **transparency label** variants by the label selection logic.
5. The decision (both signal scores, the combined score, the label, and a `content_id`) is written to the **SQLite audit log**.
6. The structured JSON response — including `content_id`, `attribution`, `confidence`, both individual signal scores, and the label text — is returned to the client.

If a creator disputes a result, **POST /appeal** takes the `content_id` and their written reasoning, updates that record's status to `under_review` in the audit log, and appends the reasoning text. No automated re-classification occurs.

## Detection Signals

Both signals report on the same scale: **1.0 = confidently human-written, 0.0 = confidently AI-generated.** A shared scale is what makes averaging the two scores meaningful rather than arbitrary.

* **Signal 1 — Groq LLM (llama-3.3-70b-versatile):** Captures holistic semantic and stylistic coherence: does the text read the way a human would write, given its content, voice, and context. This is the kind of judgment that's hard to reduce to a formula. **Blind spot:** An LLM judging text against its own internalized sense of "natural" writing may not generalize well to writing styles that are unusual but genuinely human (e.g., non-native English speakers, technical writers, intentionally terse prose) — a real risk of false positives.
* **Signal 2 — Stylometric heuristics:** Computes sentence-length variance and type-token ratio (vocabulary diversity) in pure Python. The assumption, supported by the project's own guidance, is that AI-generated text tends toward more uniform sentence rhythm and more repetitive vocabulary, while human writing varies more in both. Higher variance + higher TTR is scored as more human-like. **Blind spot:** Modern LLMs can produce text with high lexical variety and varied sentence length, which causes this signal to score clearly AI-generated text as human-like.

## Confidence Scoring

**Formula:** `combined_confidence = (0.6 * llm_score) + (0.4 * structural_score)`, rounded to 2 decimal places. The LLM signal is weighted higher because it captures holistic semantic judgment, which we judged more reliable than surface statistics alone; stylometry acts as a secondary structural check.

**Thresholds:**
* `combined_confidence >= 0.65` → `likely_human`
* `0.30 <= combined_confidence < 0.65` → `uncertain`
* `combined_confidence < 0.30` → `likely_ai`

These thresholds are intentionally asymmetric. Per the project's guidance that a false positive (mislabeling a human as AI) is more harmful than a false negative, it takes a *higher* combined score to reach `likely_human` (0.65) than it does to avoid `likely_ai` (anything ≥ 0.30 stays out of that bucket). Borderline cases default to `uncertain` rather than asserting either verdict.

### Validation — Example Submissions with Different Confidence Levels:

* **Lower-confidence case** — text written to be clearly AI-generated (*"Artificial intelligence represents a transformative paradigm shift..."*):
    * `llm_score: 0.2` | `structural_score: 0.88` | **`combined_confidence: 0.47` $\rightarrow$ `uncertain`**
    * *Analysis:* This result is the clearest evidence of how the two signals can diverge: the LLM signal correctly identified the text as AI-generated (0.2), but the stylometry signal scored it as highly human-like (0.88) because the sentence lengths varied and vocabulary was diverse. The combined score landed in "uncertain" rather than confidently flagging it as AI — a real limitation, discussed below.

* **Higher-confidence case** — casual, human-written restaurant review (*"ok so i finally tried that new ramen place downtown..."*):
    * `llm_score: 0.9` | `structural_score: 0.92` | **`combined_confidence: 0.91` $\rightarrow$ `likely_human`**
    * *Analysis:* Here both signals agree closely, producing a high-confidence result. The gap between these two examples (0.47 vs. 0.91) shows the scoring is responsive to real differences in the input rather than clustering around a constant.

## Transparency Label

The label returned to the client changes based on which threshold band the combined confidence falls into:

| Attribution Code | Verbatim System Transparency Label Text |
| :--- | :--- |
| `likely_human` | "This work appears to be human-written, based on a high-confidence analysis of writing style and content." |
| `uncertain` | "We were unable to confidently determine whether this work is human-written or AI-generated. Treat the attribution as inconclusive." |
| `likely_ai` | "This work appears to be AI-generated, based on a high-confidence analysis of writing style and content." |

## Appeals Workflow

`POST /appeal` accepts `content_id` and `creator_reasoning`. If the `content_id` exists in the audit log, the record's `status` is updated to `under_review` and the reasoning text is stored alongside the original classification. If the ID doesn't exist, the endpoint returns `404`.

### Live Verification Example:

```text
Request:
{
  "content_id": "8b62d41e-53d8-4cf5-91d0-4e63bcae066d",
  "creator_reasoning": "I wrote this myself from personal experience."
}

Response:
content_id                           message          status  
----------                           -------          ------  
8b62d41e-53d8-4cf5-91d0-4e63bcae066d Appeal received. under_review
GET /log confirms the corresponding audit entry now shows "status": "under_review" with appeal_reasoning populated. No automated re-classification occurs — review is left to a human reviewer who would query the log for under_review entries.

Rate Limiting
The /submit endpoint is limited to 10 requests per minute and 100 per day per client via Flask-Limiter using in-memory storage.

Reasoning: A genuine creator submitting their own work for attribution checking would realistically submit a handful of pieces in a sitting, not a continuous stream — 10/minute comfortably covers that pattern while making a scripted flood attack (submitting hundreds of requests per minute to probe or abuse the detection pipeline, or to run up Groq API costs) immediately visible and blocked. The 100/day ceiling caps sustained abuse across a longer window while still allowing a creator to submit many separate pieces of work over a day.

Operational Rate Limiter Evidence (12 rapid requests):
200
200
200
200
200
200
200
200
200
200
429
429
Audit Log
Every submission and appeal writes a structured record to a SQLite table (audit_logs) containing: content_id, creator_id, timestamp, text_preview, llm_score, structural_score, combined_confidence, attribution, status, and appeal_reasoning.

GET /log returns the most recent 50 entries as JSON. At minimum three submissions plus one appeal were generated during testing and are visible via this endpoint as structured JSON dictionaries inside the entries list.

Known Limitations
AI-generated text with high lexical variety can be misclassified as human-written or uncertain: This was directly observed in testing (see the 0.47-confidence example above): the stylometry signal assumes AI text is structurally uniform, but a model prompted or trained to vary its sentence length and vocabulary defeats that assumption. Because stylometry contributes 40% of the combined score, this can pull a clearly AI-generated piece out of the likely_ai band entirely. This is a structural blind spot of the signal itself, not a tuning problem — adjusting thresholds wouldn't fix a signal that is measuring the wrong thing for this case.

Short or terse human writing may score artificially low on stylometry: A human creator writing in a clipped, list-like, or minimalist style will produce low sentence-length variance and limited vocabulary diversity purely as a function of brevity, not because the writing is AI-generated. This risks the exact false-positive scenario the project's hints flagged as the more harmful error.

Spec Reflection
Writing planning.md before any code — specifically deciding that both signals needed to report on the same 0–1 "P(human)" scale — directly prevented a bug: an early draft of the code combined a raw LLM score with a structural score without confirming they meant the same thing in the same direction, which would have made the weighted average meaningless. Defining that convention explicitly in the spec first caught the mismatch before it shipped.

Where implementation diverged from the original plan: the architecture diagram described the audit log writer as setting status='valid', but the actual implementation uses status='classified' for new submissions and status='under_review' after an appeal. The diagram's wording was a draft placeholder that didn't match the two real states the system actually needs to distinguish between classified-but-unreviewed content and content currently under dispute.

AI Usage
Instance 1 — confidence scoring formula and threshold logic: I directed an AI tool to implement combined_confidence and the three-way classify() function according to the weighting and thresholds defined in planning.md. An earlier version of it (and an earlier draft of my own code) had only two branches in the classification logic, meaning the likely_ai label could never actually be returned regardless of input. I caught this by testing with a deliberately AI-leaning input and noticing the response could only ever be uncertain or likely_human, then corrected the branching to include all three thresholds.

Instance 2 — Groq signal integration and error handling: I directed an AI tool to write the signals_llm.py module, including a fallback for failed API calls. During testing, the signal kept returning the 0.5 fallback value, which the AI tool's exception handling silently swallowed. I asked it to add a debug print statement to the exception handler, which surfaced the real error (KeyError: 'GROQ_API_KEY') and let me trace the actual problem to a missing .env file and a misconfigured pip/virtualenv mismatch on my machine — issues the original silent fallback had been masking.
