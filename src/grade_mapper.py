"""
grade_mapper.py — turn camera/lens defect detections into a condition grade.

This is the "policy" layer that sits on top of the YOLO defect detector. The
detector answers "what defects are present and where"; this module answers
"so what grade is this unit". It is deliberately a transparent rule engine
(not a learned regressor) so every grade is auditable and tunable — see
docs/grading_rubric.md for the rationale and the full rubric.

The rubric here is ILLUSTRATIVE, not an official marketplace standard.

Usage
-----
As a library:

    from grade_mapper import grade_detections, Detection
    dets = [Detection("fungus", 0.91, area_fraction=0.04)]
    result = grade_detections(dets)
    print(result.grade, "—", result.reason)

From Ultralytics YOLO results:

    from ultralytics import YOLO
    from grade_mapper import grade_from_ultralytics
    r = YOLO("best.pt")("lens.jpg")[0]
    print(grade_from_ultralytics(r))

Self-test:

    python src/grade_mapper.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


# --- Class taxonomy (must match camera_lens.yaml) ---------------------------
CLASS_NAMES = [
    "pristine",
    "body_scratch",
    "paint_wear",
    "dent",
    "lens_scratch",
    "internal_dust",
    "fungus",
    "haze",
    "coating_damage",
    "screen_damage",
]

# Per-class base penalty (points off 100 for a "typical sized" defect).
# Cosmetic defects are penalized purely on score. Optical defects carry a
# moderate score penalty AND a hard grade cap (see below) — the cap is what
# guarantees that even a small, well-presented optical defect can't be graded
# "Excellent". This keeps the caps meaningful rather than redundant.
BASE_WEIGHT = {
    "pristine": 0,
    # cosmetic
    "body_scratch": 8,
    "paint_wear": 6,
    "dent": 14,
    "screen_damage": 12,
    # borderline
    "internal_dust": 4,
    # optical (moderate score hit; the hard caps below enforce severity)
    "coating_damage": 12,
    "lens_scratch": 18,
    "haze": 16,
    "fungus": 8,
}

OPTICAL_CRITICAL = {"lens_scratch", "fungus", "haze", "coating_damage"}

# Confidence below this is ignored.
DEFAULT_CONF_THRESHOLD = 0.35

# Grade bands: (min_score_inclusive, grade). Checked high → low.
GRADE_BANDS = [
    (95, "Like New"),
    (85, "Excellent"),
    (70, "Good"),
    (50, "Well Used"),
    (0, "Heavily Used"),
]

# Ordering used to apply caps (index = severity rank; lower = better).
GRADE_ORDER = ["Like New", "Excellent", "Good", "Well Used", "Heavily Used"]


@dataclass
class Detection:
    """One detected defect.

    area_fraction: bbox area as a fraction of the whole image (0..1). Used to
    scale the penalty — a tiny mark hurts less than a large one. If unknown,
    leave as None and a neutral multiplier of 1.0 is used.
    central: True if the defect bbox center is in the central region of the
    frame (matters for lens_scratch — a scratch over the optical center is worse).
    """

    class_name: str
    confidence: float = 1.0
    area_fraction: Optional[float] = None
    central: bool = False


@dataclass
class GradeResult:
    grade: str
    score: float
    reason: str
    counted: List[str] = field(default_factory=list)
    caps_applied: List[str] = field(default_factory=list)


def _severity_multiplier(area_fraction: Optional[float]) -> float:
    """Scale penalty by defect size. Clamped to [0.5, 2.5]."""
    if area_fraction is None:
        return 1.0
    # 0.02 (2% of frame) ~ typical → 1.0x; scales linearly, clamped.
    mult = 0.5 + (area_fraction / 0.02)
    return max(0.5, min(2.5, mult))


def _band_for_score(score: float) -> str:
    for threshold, grade in GRADE_BANDS:
        if score >= threshold:
            return grade
    return "Heavily Used"


def _cap(grade: str, ceiling: str) -> str:
    """Return the worse (more severe) of grade and ceiling."""
    return grade if GRADE_ORDER.index(grade) >= GRADE_ORDER.index(ceiling) else ceiling


def grade_detections(
    detections: List[Detection],
    conf_threshold: float = DEFAULT_CONF_THRESHOLD,
) -> GradeResult:
    """Apply the rubric to a list of detections and return a GradeResult."""
    kept = [d for d in detections if d.confidence >= conf_threshold]
    # 'pristine' detections carry no penalty and are informational only.
    defects = [d for d in kept if d.class_name != "pristine" and d.class_name in BASE_WEIGHT]

    score = 100.0
    counted = []
    for d in defects:
        penalty = BASE_WEIGHT[d.class_name] * _severity_multiplier(d.area_fraction)
        score -= penalty
        counted.append(f"{d.class_name}(-{penalty:.0f})")
    score = max(0.0, score)

    grade = _band_for_score(score)

    # --- Optical-critical hard caps ---
    caps = []
    if any(d.class_name == "fungus" and (d.area_fraction or 0) >= 0.06 for d in defects):
        grade = _cap(grade, "Heavily Used")
        caps.append("widespread fungus → Heavily Used cap")
    elif any(d.class_name == "fungus" for d in defects):
        grade = _cap(grade, "Well Used")
        caps.append("fungus → Well Used cap")
    if any(d.class_name == "haze" and (d.area_fraction or 0) >= 0.05 for d in defects):
        grade = _cap(grade, "Well Used")
        caps.append("large haze → Well Used cap")
    if any(d.class_name == "lens_scratch" and d.central for d in defects):
        grade = _cap(grade, "Good")
        caps.append("central lens scratch → Good cap")

    if not defects:
        reason = "No defects above confidence threshold."
    else:
        reason = f"Defects: {', '.join(counted)}."
        if caps:
            reason += f" Caps: {', '.join(caps)}."

    return GradeResult(
        grade=grade,
        score=round(score, 1),
        reason=reason,
        counted=counted,
        caps_applied=caps,
    )


def grade_from_ultralytics(result, conf_threshold: float = DEFAULT_CONF_THRESHOLD) -> GradeResult:
    """Adapt an Ultralytics `Results` object into a GradeResult.

    `result` is one element of the list returned by a YOLO model call.
    """
    dets: List[Detection] = []
    boxes = getattr(result, "boxes", None)
    if boxes is None:
        return grade_detections([], conf_threshold)

    names = result.names  # {id: name}
    h, w = result.orig_shape  # (height, width)
    img_area = float(h * w)

    for b in boxes:
        cls_id = int(b.cls[0])
        conf = float(b.conf[0])
        x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
        area_fraction = ((x2 - x1) * (y2 - y1)) / img_area if img_area else None
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        central = (0.3 * w <= cx <= 0.7 * w) and (0.3 * h <= cy <= 0.7 * h)
        dets.append(
            Detection(
                class_name=names.get(cls_id, str(cls_id)),
                confidence=conf,
                area_fraction=area_fraction,
                central=central,
            )
        )
    return grade_detections(dets, conf_threshold)


# --- Self-test --------------------------------------------------------------
if __name__ == "__main__":
    scenarios = {
        "Clean unit": [Detection("pristine", 0.98)],
        "One small body scratch": [Detection("body_scratch", 0.8, area_fraction=0.01)],
        "Worn but clean glass": [
            Detection("paint_wear", 0.7, area_fraction=0.02),
            Detection("paint_wear", 0.6, area_fraction=0.02),
            Detection("internal_dust", 0.5, area_fraction=0.005),
        ],
        "Large haze": [Detection("haze", 0.85, area_fraction=0.08)],
        "Fungus, otherwise clean": [Detection("fungus", 0.91, area_fraction=0.03)],
        "Central scratch + dents": [
            Detection("lens_scratch", 0.9, area_fraction=0.04, central=True),
            Detection("dent", 0.8, area_fraction=0.03),
            Detection("dent", 0.7, area_fraction=0.02),
        ],
    }
    print(f"{'Scenario':<28} {'Score':>6}  {'Grade':<14} Reason")
    print("-" * 90)
    for name, dets in scenarios.items():
        r = grade_detections(dets)
        print(f"{name:<28} {r.score:>6}  {r.grade:<14} {r.reason}")
