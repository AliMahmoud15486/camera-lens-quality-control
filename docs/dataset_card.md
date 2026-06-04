# Dataset Card — Camera & Lens Cosmetic Defect Dataset

> **Status: to be built.** This card is the *specification and capture protocol*
> for the dataset, written before collection so the data is consistent from day
> one. Fields marked **TBD** are filled in as the dataset is captured. The
> structure follows the source bottle-QC dataset card.

---

## Dataset summary

An image dataset for **cosmetic and optical defect detection** on used cameras and
lenses, intended to fine-tune a YOLO detector whose output feeds the condition
[grading rubric](grading_rubric.md). Every image is to be staged, captured, and
annotated under a fixed protocol — no scraped or synthetic data.

---

## Dataset details

| Field | Value |
|---|---|
| **Total images** | TBD |
| **Number of classes** | 10 |
| **Annotation format** | YOLO (normalized `x_center y_center width height`) |
| **Image resolution** | TBD (capture ≥ 3000 px on long edge) |
| **Capture device** | TBD |
| **Annotation tool** | CVAT (or Label Studio) |
| **Dataset version** | 0.1 (spec) |

---

## Classes

| ID | Name | Family | Description |
|---|---|---|---|
| 0 | `pristine` | — | No visible cosmetic or optical defect |
| 1 | `body_scratch` | Cosmetic | Scratches / scuffs on body, barrel, filter ring |
| 2 | `paint_wear` | Cosmetic | Brassing / paint loss on edges and mounts |
| 3 | `dent` | Cosmetic | Dents / dings on body, barrel, filter thread |
| 4 | `lens_scratch` | Optical | Scratch / mark on a front or rear glass element |
| 5 | `internal_dust` | Borderline | Dust specks inside the lens elements |
| 6 | `fungus` | Optical | Fungal growth (web/branch pattern) inside the lens |
| 7 | `haze` | Optical | Internal haze / cloudiness on elements |
| 8 | `coating_damage` | Optical | Coating scratches, marks, oil, cleaning marks |
| 9 | `screen_damage` | Cosmetic | Scratches / cracks on LCD or top display |

---

## Capture protocol

Unlike the source bottle dataset (one lighting setup), camera/lens QC needs
**multiple lighting modalities** because cosmetic and optical defects reveal
themselves under different light.

### Cosmetic defects (body, barrel, screen)

- **Lighting:** diffuse, even illumination (softbox / light tent) to read paint
  wear and dents without glare.
- **Background:** neutral matte (grey/black) for contrast.
- **Angles:** capture each face; include raking-light passes for shallow scratches
  that vanish under flat light.

### Optical defects (glass elements)

- **Internal dust / fungus:** shine a **focused light through or across the front
  element** in a dark environment; dust and fungus light up against the dark glass.
- **Haze:** **transmitted light** (light source behind the lens, shooting through
  it) — haze appears as a milky veil.
- **Coating damage:** angle the element under a **single hard light** and rotate to
  catch coating scratches as colored streaks.

> The capture modality should be recorded per image (e.g. filename prefix
> `cos_`, `dark_`, `trans_`) so optical-defect crops aren't mixed with flat-light
> cosmetic shots during analysis.

---

## Annotation process

Each defect instance gets a **tight bounding box** with the appropriate class. A
clean unit gets a single `pristine` box over the item. Guidance:

- Label **every** visible instance, not just the worst one (multiple dust specks =
  multiple boxes, or one box around a cluster — pick one convention and hold it).
- For diffuse defects (haze), box the **affected region**, not the whole lens.
- Record `central` vs. peripheral for `lens_scratch` (the grader treats a
  center-of-frame scratch as worse — see the rubric).

**Label format:** YOLO `.txt`, one file per image, one line per box:
```
<class_id> <x_center> <y_center> <width> <height>
```
All values normalized to `[0, 1]`. (The pipeline normalizes float class IDs like
`4.0 → 4` — see [engineering_debrief.md](engineering_debrief.md), Bug 2.)

---

## Augmentation strategy

Albumentations to balance toward **250 samples/class**. Carry over the source
project's hard-won constraints:

- Conservative `Affine` (`translate_percent ≤ 0.03`) to avoid invalid boxes
  (debrief Bug 4).
- Post-augmentation validity scan: reject any box outside `[0,1]` or with
  non-positive dimensions.
- ⚠️ **Domain caution:** some transforms can *destroy* the defect signal.
  Heavy blur erases fine scratches; aggressive hue/saturation shifts can mask
  fungus coloration or invent fake haze. Validate augmented optical-defect samples
  visually before trusting them.

---

## Dataset integrity

Fingerprint the raw label directory with **SHA-256** at the start of every run and
store the prefix in `model_card.json` for reproducibility. (SHA-256 prefix: **TBD**.)

---

## Train / validation split

Grouped by original image stem so augmented variants never leak across the split.
Target ratio **85% train / 15% validation**. (Counts: **TBD**.)

---

## Limitations

- Optical defects are the hardest to capture consistently; dataset quality will
  hinge on the lighting protocol above more than on model choice.
- Sourcing genuinely defective gear (fungus, element scratches) is harder than
  staging bottle defects — expect class imbalance skewed toward cosmetic classes.
- Visual-only: no functional/mechanical condition is represented in this dataset.

---

*Dataset spec by Ali Mahmoud. Structure adapted from the Big Cola Bottles dataset card by Youssef El Demerdash.*
