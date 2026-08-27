"""State transition helpers for a deterministic scripted vehicle stop."""

from __future__ import annotations

import math


def advance_stop_lock(
    *,
    braking: bool,
    speed_kmh: float,
    locked: bool,
    below_threshold_steps: int,
    speed_threshold_kmh: float = 1.0,
    confirmation_steps: int = 3,
):
    """Advance the lead-vehicle stop-lock state by one simulation step.

    A lock is only engaged after the scripted brake is active and the measured
    speed remains below the threshold for ``confirmation_steps`` consecutive
    samples.  Once engaged it is sticky for the remainder of the brake phase;
    this prevents a transient physics impulse from reopening the controller.
    """
    threshold = float(speed_threshold_kmh)
    required = int(confirmation_steps)
    if not math.isfinite(threshold) or threshold <= 0:
        raise ValueError("speed_threshold_kmh 必须是正数")
    if required < 1:
        raise ValueError("confirmation_steps 必须是正整数")

    if not braking:
        return {
            "locked": False,
            "below_threshold_steps": 0,
            "just_locked": False,
        }
    if locked:
        return {
            "locked": True,
            "below_threshold_steps": max(0, int(below_threshold_steps)),
            "just_locked": False,
        }

    try:
        speed = float(speed_kmh)
    except (TypeError, ValueError):
        speed = math.inf
    if math.isfinite(speed) and speed <= threshold:
        samples = max(0, int(below_threshold_steps)) + 1
    else:
        samples = 0
    newly_locked = samples >= required
    return {
        "locked": newly_locked,
        "below_threshold_steps": samples,
        "just_locked": newly_locked,
    }
