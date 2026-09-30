# Detection Pipeline — Tuning Guide

This document explains the 5-layer false-positive defence implemented in
`services/video_service.py`, and which knob to turn when a client reports
"too many false positives" or "missed a real incident".

## 0. Write good prompts FIRST (most common cause of missed detections)

X-CLIP is a **visual similarity** model. It matches video frames against
text **descriptions of what is visible**. It is NOT an instruction-following
chatbot. The single biggest cause of missed detections is operators
phrasing prompts as instructions or questions:

| Bad prompt (won't work) | Good prompt (will work) |
|---|---|
| "Check if there is any theft" | "a person stealing items" |
| "If more than 1 person" | "multiple people in a room" |
| "check if any thieves" | "thieves robbing a house at night" |
| "Detect weapons" | "a person holding a gun" |
| "Is anyone fighting" | "two people punching each other" |

**Rules of thumb:**
- 4–10 words, present tense, describes what you'd SEE in a frame.
- Concrete nouns + visible action. "a person doing X" / "people Y".
- One scene type per prompt — split "fighting OR stealing" into two prompts.
- Avoid "check", "detect", "is there", "if", question marks.

**Recommended starter set** for general security cameras (paste these
into Manage Prompts; all marked Suspicious unless noted):

```
a person stealing items from a room          [suspicious]
a person breaking into a building            [suspicious]
thieves robbing a property at night          [suspicious]
masked intruders inside a building           [suspicious]
a person holding a gun                       [suspicious]
a person holding a knife                     [suspicious]
two people punching each other               [suspicious]
people fighting violently                    [suspicious]
a person walking through the area            [normal]
a person standing in the scene               [normal]
```

## 1. The "Suspicious Threshold" slider (Video Analysis page)

The slider is a **live sensitivity dial** that overrides the category
confidence floor. Use it when X-CLIP can't get confident enough on your
footage (e.g. dark/grainy CCTV, partial occlusion, unusual camera angle).

| Slider value | Effect | Use when |
|---|---|---|
| **0.20** | Catches almost anything that even slightly matches | Low-quality CCTV, dark footage, prompts that the model struggles with |
| **0.40** | More sensitive; some false positives | Default for difficult environments |
| **0.60** | Balanced (recommended default) | Good lighting, clear scenes |
| **0.80** | Strict; only high-confidence detections | Reviewing critical footage, want zero noise |

The slider only affects the **confidence floor and anchor margin** — the
motion gates and sustained-detection logic always run, so the
handshake-as-fight defence still works even at slider=0.20.

## The five gates

A per-window detection only fires ALERT when **all five** of these pass:

| # | Gate | File / constant | What it catches |
|---|------|-----------------|-----------------|
| 1 | **Confidence floor** (`min_prob`) | `CATEGORY_THRESHOLDS` | Low-confidence noise. |
| 2 | **Anchor margin** | `CATEGORY_THRESHOLDS.anchor_margin` + `ANCHOR_PROMPTS` | Handshake/hug/phone scoring high on `fight`/`weapon` prompts. The suspicious prompt must beat the strongest anchor by this margin. |
| 3 | **Motion gates** | `MOTION_GATES` | Coherent (handshake) or near-static (still object) scenes that score high on violence/weapon prompts. |
| 4 | **Sustained-detection (temporal)** | `TemporalSmoothing.DEFAULTS.consecutive` | Single-window blips (1.5–3s handshakes). |
| 5 | **Verdict-level longest-run** | `calculate_verdict()` | Verdict tiers (CRITICAL/HIGH) require both % suspicious AND a minimum longest consecutive run. |

## Anchor prompts (`ANCHOR_PROMPTS`)

Hidden prompts injected into every X-CLIP call alongside operator
prompts. They give softmax mass somewhere legitimate to flow when the
scene is non-threatening but superficially similar to a suspicious one.

The operator never sees these. They are stripped from the
"current label" displayed in the UI. They only influence scoring via
the anchor-margin gate.

Add an anchor here whenever a new false-positive pattern is reported:

```python
ANCHOR_PROMPTS = [
    "two people shaking hands",   # ← absorbs probability mass that
    "two people hugging",         #   would otherwise leak into "fight"
    ...
]
```

Keep them short (3–8 words). X-CLIP is a CLIP-family model — long
instruction sentences degrade the embedding.

## Category thresholds

```python
CATEGORY_THRESHOLDS = {
    'weapon':    {'min_prob': 0.80, 'anchor_margin': 0.20},
    'violence':  {'min_prob': 0.75, 'anchor_margin': 0.15},
    'theft':     {'min_prob': 0.72, 'anchor_margin': 0.12},
    'intrusion': {'min_prob': 0.72, 'anchor_margin': 0.12},
    'default':   {'min_prob': 0.70, 'anchor_margin': 0.10},
}
```

- **`min_prob`** ─ the top suspicious softmax probability must be at least this.
- **`anchor_margin`** ─ top suspicious prob must exceed the strongest anchor prob by at least this.

Categorisation is keyword-based (`_categorize_prompt`). Operator
prompts containing "fight"/"punch"/"violence" → `violence`. "gun"/
"knife"/"weapon" → `weapon`. Everything else → `default`.

## Motion gates

```python
MOTION_GATES = {
    'violence':  {'min_peak': 3.0, 'min_direction_variance': 0.50, 'min_foreground_ratio': 0.02},
    'weapon':    {'min_foreground_ratio': 0.015},
    'theft':     {'min_foreground_ratio': 0.01},
    'intrusion': {'min_foreground_ratio': 0.01},
    'default':   {},
}
```

Computed by `MotionAnalyzer` using Farneback optical flow inside an
MOG2 foreground mask (downscaled for speed). Features:

| Feature | Meaning | Handshake | Fight |
|---------|---------|-----------|-------|
| `peak_magnitude` | 95th-percentile flow magnitude | 1.5–3 px | 5–15 px |
| `direction_variance` | Circular variance of flow direction (0..1) | 0.2–0.45 (coherent) | 0.55–0.9 (chaotic) |
| `foreground_ratio` | Fraction of moving pixels | 0.02–0.05 | 0.05–0.15 |

A scene with `peak_magnitude < 3.0` OR `direction_variance < 0.50` is
not classified as violence even when the VLM is highly confident.

## Temporal sustained-detection

```python
TemporalSmoothing.DEFAULTS = {
    'weapon':    {'high': 0.78, 'low': 0.50, 'consecutive': 2},
    'violence':  {'high': 0.72, 'low': 0.50, 'consecutive': 2},
    'theft':     {'high': 0.70, 'low': 0.45, 'consecutive': 2},
    'intrusion': {'high': 0.68, 'low': 0.45, 'consecutive': 1},
    'default':   {'high': 0.65, 'low': 0.45, 'consecutive': 1},
}
```

- `high` / `low`  ─ hysteresis thresholds (enter alert / leave alert).
- `consecutive`   ─ number of windows above `high` required to flip into alert.

A handshake lasting 1–3 seconds produces at most 1 inference window above
`high`. With `consecutive: 2` for violence, that blip can never alert.

## Verdict longest-run

```python
if suspicious_pct >= 30 and longest_run >= 3: CRITICAL
elif suspicious_pct >= 18 and longest_run >= 2: HIGH
elif suspicious_pct >= 8  or  longest_run >= 2: MEDIUM
elif suspicious_pct >= 2  or  longest_run >= 1: LOW
else: CLEAR
```

The `longest_run` constraint means an isolated stray window cannot push
the video into CRITICAL/HIGH no matter how short the video is.

## Tuning recipes

### "Still too many handshake → fight false positives"

1. Add more friendly-contact anchors to `ANCHOR_PROMPTS`.
2. Raise `CATEGORY_THRESHOLDS['violence']['anchor_margin']` from 0.15 → 0.20.
3. Raise `MOTION_GATES['violence']['min_direction_variance']` from 0.50 → 0.60.

### "Missing real fights"

1. Lower `CATEGORY_THRESHOLDS['violence']['min_prob']` from 0.75 → 0.70.
2. Lower `MOTION_GATES['violence']['min_peak']` from 3.0 → 2.5.
3. Reduce `TemporalSmoothing.DEFAULTS['violence']['consecutive']` from 2 → 1.
   (Trades sustained-detection for sensitivity.)

### "Weapon false positives on phones"

1. Add specific anchors: `"a person holding a smartphone"`, `"a person texting on a phone"`.
2. Raise `CATEGORY_THRESHOLDS['weapon']['min_prob']` from 0.80 → 0.85.

## Diagnosing a single video

Per-window decisions are logged at INFO level. Each line includes:

```
Frame N/M | ALERT: <label> (XX%) | top=0.82 margin=+0.71 |
motion: peak=6.45 dirvar=0.78 fg=0.092 | consec=2/2 (hi=0.72) | all_gates_passed
```

If a video isn't flagged when it should be, grep `vigilinx.log` for the
relevant frames and look at the `reason` field. Common reasons:

| `reason` | Fix |
|----------|-----|
| `below_min_prob(...)` | VLM not confident enough — try better prompts or lower `min_prob`. |
| `anchor_too_close(...)` | An anchor competed too well — sometimes legitimate; sometimes prompt phrasing is too close to an anchor. |
| `coherent_motion(...)` | Motion looks like friendly contact. If wrong, lower `min_direction_variance`. |
| `low_peak_motion(...)` | Not enough peak velocity. Lower `min_peak` for slow-mo footage. |
| `scene_too_static(...)` | Camera or scene mostly still. Common in good-quality recordings — tune `min_foreground_ratio` down. |

## Future improvements (not implemented yet)

- **Operator feedback loop**: a "Mark as false positive" button on
  verdicts in the UI, persisted to a `false_positives` table.
  At inference time, dampen scores near known-FP embeddings.
- **Pose-based verifier**: MediaPipe Pose on candidate-positive windows
  only. Wrist velocity + body-tilt asymmetry would catch the remaining
  long-tail cases. Adds ~50 MB to the `.deb`.
- **Fine-tune X-CLIP** on a curated handshake/hug/fight dataset for
  the operator's specific environment (lobby, retail, parking lot, ...).
