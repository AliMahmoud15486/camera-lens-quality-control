# Grading Rubric — Detected Defects → Condition Grade

This is the bridge between **computer-vision output** (defect detections) and a
**business-facing condition grade**. It is what makes a defect detector useful
for a used-gear marketplace: a model that says "fungus, 0.91 confidence, bbox at
(x,y,w,h)" is only valuable once that becomes "this lens is **Well Used**."

> ⚠️ **Illustrative, not official.** The grade bands and weights below are a
> reasonable starting rubric for *cosmetic/optical* assessment from images. They
> are **not** MPB's official grading standard. Real grading also depends on
> functional/mechanical checks (shutter count, autofocus, aperture blades,
> electronic contacts) that cannot be judged from a photo. This rubric only
> covers what is *visually detectable*.

---

## Condition grades

A five-band scale aligned to the vocabulary used across the used-camera market:

| Grade | Meaning |
|---|---|
| **Like New** | Indistinguishable from new. No visible cosmetic or optical defects. |
| **Excellent** | Minimal signs of use. Tiny cosmetic marks only; optically clean. |
| **Good** | Clear signs of use but fully functional. Cosmetic wear and/or trivial internal dust. |
| **Well Used** | Heavy cosmetic wear, or a minor optical defect that may have slight image impact. |
| **Heavily Used** | Significant optical defects (fungus / haze / element scratches) likely to affect image quality. |

---

## Two defect families

Defects are split by **what they affect**, because the market penalizes them very differently:

| Family | Classes | Why it matters |
|---|---|---|
| **Cosmetic** | `body_scratch`, `paint_wear`, `dent`, `screen_damage` | Affects appearance/resale, not image quality. Penalized lightly. |
| **Optical** | `lens_scratch`, `fungus`, `haze`, `coating_damage` | Can degrade the actual photographs. Penalized heavily, with hard caps. |
| **Borderline** | `internal_dust` | A small amount is normal and harmless; only large quantities matter. |

---

## Scoring model

Each unit starts at **100 points**. Every detection subtracts a penalty:

```
penalty(detection) = base_weight[class] × severity_multiplier(bbox_area_fraction)
```

- `base_weight` — per-class severity (see [grade_mapper.py](../src/grade_mapper.py)).
- `severity_multiplier` — scales penalty by how large the defect is relative to
  the frame (a 2 mm scratch ≠ a barrel-length gouge).
- Detections below a confidence threshold (default `0.35`) are ignored.

### Score → grade bands

| Final score | Grade |
|---|---|
| ≥ 95 | Like New |
| 85 – 94 | Excellent |
| 70 – 84 | Good |
| 50 – 69 | Well Used |
| < 50 | Heavily Used |

### Hard caps (optical-critical overrides)

Some optical defects cap the grade regardless of score, because they materially
affect image quality:

| Condition | Grade cannot exceed |
|---|---|
| Any `fungus` detected | **Well Used** |
| `haze` covering a large area | **Well Used** |
| `lens_scratch` on a central element area | **Good** |

A unit with a pristine score but confirmed fungus is **not** "Excellent" — the
cap pulls it down to "Well Used" because fungus spreads and etches coatings.

---

## Worked examples

These are the exact outputs of the `grade_mapper.py` self-test (`python src/grade_mapper.py`):

| Detections | Score | Cap applied | Final grade |
|---|---|---|---|
| `pristine` only | 100 | — | Like New |
| 1× small `body_scratch` | 92 | — | Excellent |
| 2× `paint_wear` + small `internal_dust` | 79 | — | Good |
| 1× `haze` (large) | 60 | Well Used cap | Well Used |
| 1× `fungus` + clean otherwise | 84 | Well Used cap | Well Used |
| `lens_scratch` (large, central) + 2× `dent` | 6 | central-scratch cap (non-binding) | Heavily Used |

---

## Why a rule engine, not a regression model

A learned "image → grade" regressor would be a black box that a marketplace
operations team cannot audit or appeal. A transparent rule engine over detected
defects means every grade comes with a **reason string** ("Well Used — fungus
detected (optical cap)"), which is reviewable, contestable, and tunable without
retraining. The detector handles perception; the rubric handles policy.
