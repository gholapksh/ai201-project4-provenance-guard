# System Specification: Provenance Guard

This document establishes the architecture, calibration algorithms, user experience thresholds, and safety protocols for the Provenance Guard backend engine.

---

## 🗺️ Architecture

### Process Flow Diagram

```text
1. SUBMISSION PIPELINE FLOW (POST /submit)
========================================================================================
[Client Text Content]
          │
          ▼
   ┌──────────────┐
   │ Rate Limiter │ ───(Exceeded)───> [429 Too Many Requests]
   └──────────────┘
          │ (Within Limits)
          ▼
   ┌────────────────────────────────────────────────────────┐
   │              Multi-Signal Detection Engine             │
   │                                                        │
   │  ┌───────────────────────┐   ┌──────────────────────┐  │
   │  │ Signal 1: Groq LLM    │   │ Signal 2: Stylometry │  │
   │  │ Holistic Semantics    │   │ Structural Metrics   │  │
   │  │ Output: 0.0 to 1.0    │   │ Output: 0.0 to 1.0   │  │
   │  └───────────────────────┘   └──────────────────────┘  │
   └───────────────────────────┬────────────────────────────┘
                               │
                               ▼
               ┌───────────────────────────────┐
               │ Unified Calibration Engine    │
               │ Weighted Formula Calculation  │
               └───────────────┬───────────────┘
                               │ (Combined Score)
                               ▼
               ┌───────────────────────────────┐
               │ UX Label Selection Component  │
               │ Maps Score to Text Variant    │
               └───────────────┬───────────────┘
                               │
                               ▼
               ┌───────────────────────────────┐
               │     SQLite Audit Log Writer   │
               │ Creates Record: status='valid'│
               └───────────────┬───────────────┘
                               │
                               ▼
               [Structured JSON Response Payload]


2. APPEALS PIPELINE FLOW (POST /appeal)
========================================================================================
[Client content_id + Reasoning]
          │
          ▼
   ┌──────────────┐
   │ ID Validator │ ───(Not Found)───> [404 Record Not Found]
   └──────────────┘
          │ (Valid ID)
          ▼
   ┌────────────────────────────────────────────────────────┐
   │               Audit Log State Machine                  │
   │ • Updates record status flag to 'under_review'         │
   │ • Appends raw 'appeal_reasoning' string text           │
   └───────────────────────────┬────────────────────────────┘
                               │
                               ▼
               [Structured JSON Confirmation Payload]
## Detection Signals

Both signals output a score on the same 0.0–1.0 scale, where **1.0 = confidently 
human-written** and **0.0 = confidently AI-generated**. Using a shared scale is 
required for the weighted average to be meaningful — averaging two scores that 
mean different things produces noise, not a calibrated result.

**Signal 1: Groq LLM (llama-3.3-70b-versatile)**
Measures holistic semantic and stylistic coherence — does the text "read" as 
something a human would write, given context, voice, and content. Captures 
properties that are hard to express as a formula (tone, idiosyncrasy, lived 
specificity). Blind spot: an AI model judging AI-generated text is judging 
against its own internal sense of "natural," which may not generalize to all 
human writing styles (e.g. ESL writers, technical writers) — risk of false 
positives against unusual-but-human prose.

**Signal 2: Stylometric heuristics (sentence length variance + type-token ratio)**
Measures structural/statistical properties: how much sentence length varies, 
and how lexically diverse the vocabulary is. AI-generated text tends toward 
uniform sentence rhythm and repeated vocabulary; human writing is messier and 
more variable. Higher variance + higher TTR → scored as more human-like. 
Blind spot: short or terse human writing (e.g. casual texts, lists) can score 
low on variance/diversity purely due to length, not because it's AI-generated.

**Combination formula:**
combined_confidence = (0.6 * llm_score) + (0.4 * structural_score)

LLM signal is weighted higher (60%) because it captures holistic semantic 
judgment; stylometry (40%) acts as a structural cross-check rather than a 
primary signal, since pure statistics are easier for AI text to accidentally 
satisfy (e.g. a model prompted for "varied sentence length" would pass 
stylometry but still be AI-generated).

## Uncertainty Representation

Thresholds are chosen to reflect the false-positive asymmetry described in the 
project hints: wrongly labeling a human's work as AI-generated is more harmful 
to a creator than the reverse, so the "likely_ai" band requires a *lower* score 
(more confidence) to trigger than the "likely_human" band does.

- `combined_confidence >= 0.65` → **likely_human**
- `0.30 <= combined_confidence < 0.65` → **uncertain**
- `combined_confidence < 0.30` → **likely_ai**

A score of 0.6, for example, falls in "uncertain" even though it leans human — 
the system defaults to caution rather than asserting a verdict near the boundary.
