"""Reproducible multi-scene plans and samplers for CARLA online RL.

The plan is deliberately independent of CARLA.  It freezes the scene split,
records and provenance before an expensive runtime job is started.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import numpy as np

from core.adversarial_sampling import library_entry_to_record, load_library_entries
from core.scenario_validator import require_valid_scenario


PLAN_FORMAT = "carla_online_rl_multiscene_plan_v1"
SAMPLER_STATE_FORMAT = "carla_online_rl_sampler_state_v2"
SPLITS = ("train", "dev", "test")
DEFAULT_FRACTIONS = {"train": 0.6, "dev": 0.2, "test": 0.2}


class CarlaRLPlanError(ValueError):
    """Raised when a frozen multi-scene plan is invalid."""


def _canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _plan_digest(plan):
    unsigned = copy.deepcopy(plan)
    unsigned.pop("plan_sha256", None)
    return hashlib.sha256(_canonical_json(unsigned).encode("utf-8")).hexdigest()


def _allocate_counts(size, fractions):
    if size < len(SPLITS):
        raise CarlaRLPlanError(
            f"每个分层至少需要 {len(SPLITS)} 条记录，实际为 {size}"
        )
    weights = np.asarray([float(fractions[name]) for name in SPLITS], dtype=float)
    if np.any(weights <= 0) or not np.isclose(weights.sum(), 1.0):
        raise CarlaRLPlanError("split fractions 必须为正数且总和为 1")
    counts = np.floor(size * weights).astype(int)
    for index in range(len(SPLITS)):
        if counts[index] == 0:
            counts[index] = 1
    while int(counts.sum()) > size:
        candidates = [
            index for index, count in enumerate(counts) if count > 1
        ]
        if not candidates:
            raise CarlaRLPlanError("无法在每个 split 非空的条件下分配记录")
        index = max(candidates, key=lambda item: (counts[item] - size * weights[item], counts[item]))
        counts[index] -= 1
    remainders = size * weights - np.floor(size * weights)
    while int(counts.sum()) < size:
        index = int(np.argmax(remainders))
        counts[index] += 1
        remainders[index] = -1.0
    return {name: int(counts[index]) for index, name in enumerate(SPLITS)}


def _entry_seed(entry, seed):
    values = sorted(
        int(value)
        for value in entry.get("execution_evidence", {}).get("traffic_manager_seeds", [])
    )
    if not values:
        raise CarlaRLPlanError(
            f"{entry.get('canonical_sample_id')}: execution_evidence 缺少 traffic_manager_seeds"
        )
    digest = hashlib.sha256(
        f"{int(seed)}:{entry.get('canonical_sample_id')}".encode("utf-8")
    ).digest()
    return values[int.from_bytes(digest[:8], "big") % len(values)]


def _validate_unique(entries):
    seen_ids = {}
    seen_hashes = {}
    for entry in entries:
        canonical_id = str(entry.get("canonical_sample_id") or "").strip()
        scenario_hash = str(entry.get("scenario_hash") or "").strip()
        if not canonical_id:
            raise CarlaRLPlanError("场景缺少 canonical_sample_id")
        if canonical_id in seen_ids:
            raise CarlaRLPlanError(f"canonical_sample_id 重复: {canonical_id}")
        seen_ids[canonical_id] = entry
        if scenario_hash:
            if scenario_hash in seen_hashes:
                other = seen_hashes[scenario_hash]
                raise CarlaRLPlanError(
                    f"scenario_hash 重复，禁止场景泄漏: {other} / {canonical_id}"
                )
            seen_hashes[scenario_hash] = canonical_id


def build_multiscene_plan(
    entries_path,
    manifest_path,
    output_path=None,
    *,
    seed=20260824,
    fractions=None,
):
    """Build a deterministic, stratified train/dev/test plan."""
    entries = load_library_entries(entries_path)
    manifest_file = Path(manifest_path).expanduser().resolve()
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CarlaRLPlanError(f"无法读取场景库 manifest: {manifest_file}") from exc
    expected_count = int(manifest.get("entry_count", 0))
    if expected_count and expected_count != len(entries):
        raise CarlaRLPlanError(
            f"场景库 manifest entry_count 不一致: {expected_count} != {len(entries)}"
        )
    _validate_unique(entries)
    fractions = dict(DEFAULT_FRACTIONS, **(fractions or {}))
    unknown = set(fractions) - set(SPLITS)
    if unknown:
        raise CarlaRLPlanError(f"未知 split: {sorted(unknown)}")

    grouped = {}
    for entry in entries:
        try:
            generator = str(entry["labels"]["generators"][0])
            risk = str(entry["labels"]["target_risk_levels"][0])
        except (KeyError, IndexError, TypeError) as exc:
            raise CarlaRLPlanError("场景缺少单值 generator/target_risk_level 标签") from exc
        grouped.setdefault((generator, risk), []).append(entry)

    rng = np.random.default_rng(int(seed))
    splits = {name: [] for name in SPLITS}
    strata_summary = {}
    for stratum in sorted(grouped):
        group = list(grouped[stratum])
        counts = _allocate_counts(len(group), fractions)
        permutation = rng.permutation(len(group)).tolist()
        shuffled = [group[index] for index in permutation]
        cursor = 0
        strata_summary[f"{stratum[0]}__{stratum[1]}"] = {
            "available_count": len(group),
            "split_counts": counts,
        }
        for split in SPLITS:
            for entry in shuffled[cursor : cursor + counts[split]]:
                record = library_entry_to_record(
                    entry,
                    traffic_manager_seed=_entry_seed(entry, seed),
                    created_at=f"carla_rl_plan_seed_{int(seed)}",
                )
                # The project record schema calls the development split "validation".
                record["provenance"]["split"] = "validation" if split == "dev" else split
                require_valid_scenario(record)
                splits[split].append(
                    {
                        "library_id": entry["library_id"],
                        "canonical_sample_id": entry["canonical_sample_id"],
                        "scenario_hash": entry.get("scenario_hash"),
                        "split": split,
                        "generator": stratum[0],
                        "target_risk_level": stratum[1],
                        "record": record,
                    }
                )
            cursor += counts[split]

    ids_by_split = {
        split: {row["canonical_sample_id"] for row in rows}
        for split, rows in splits.items()
    }
    for left_index, left in enumerate(SPLITS):
        for right in SPLITS[left_index + 1 :]:
            overlap = ids_by_split[left] & ids_by_split[right]
            if overlap:
                raise CarlaRLPlanError(f"split 场景泄漏: {sorted(overlap)}")

    hashes_by_split = {
        split: {row["scenario_hash"] for row in rows if row.get("scenario_hash")}
        for split, rows in splits.items()
    }
    hash_overlap_count = 0
    for left_index, left in enumerate(SPLITS):
        for right in SPLITS[left_index + 1 :]:
            hash_overlap_count += len(hashes_by_split[left] & hashes_by_split[right])

    plan = {
        "format": PLAN_FORMAT,
        "schema_version": "1.0",
        "seed": int(seed),
        "fractions": {name: float(fractions[name]) for name in SPLITS},
        "source": {
            "entries_path": str(Path(entries_path).expanduser().resolve()),
            "manifest_path": str(Path(manifest_path).expanduser().resolve()),
            "entry_count": len(entries),
            "manifest_entry_count": expected_count,
        },
        "strata": strata_summary,
        "counts": {split: len(rows) for split, rows in splits.items()},
        "splits": splits,
        "leakage_check": {
            "canonical_sample_id_overlap": 0,
            "scenario_hash_overlap": hash_overlap_count,
        },
        "evidence_kind": "offline_frozen_split",
    }
    if hash_overlap_count:
        raise CarlaRLPlanError("scenario_hash 在 split 间重复，禁止场景泄漏")
    plan["plan_sha256"] = _plan_digest(plan)
    if output_path is not None:
        output = Path(output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return plan


def load_multiscene_plan(path):
    path = Path(path).expanduser().resolve()
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CarlaRLPlanError(f"无法读取多场景计划: {path}") from exc
    if plan.get("format") != PLAN_FORMAT:
        raise CarlaRLPlanError("不是 carla_online_rl_multiscene_plan_v1")
    if plan.get("plan_sha256") != _plan_digest(plan):
        raise CarlaRLPlanError("多场景计划哈希不匹配，禁止训练")
    for split in SPLITS:
        if not isinstance(plan.get("splits", {}).get(split), list) or not plan["splits"][split]:
            raise CarlaRLPlanError(f"{split} split 不能为空")
        for row in plan["splits"][split]:
            expected_record_split = "validation" if split == "dev" else split
            if row.get("split") != split or row.get("record", {}).get("provenance", {}).get("split") != expected_record_split:
                raise CarlaRLPlanError(f"{split} split provenance 不一致")
            require_valid_scenario(row["record"])
    ids = {split: {row["canonical_sample_id"] for row in plan["splits"][split]} for split in SPLITS}
    hashes = {
        split: {row.get("scenario_hash") for row in plan["splits"][split] if row.get("scenario_hash")}
        for split in SPLITS
    }
    for index, left in enumerate(SPLITS):
        for right in SPLITS[index + 1 :]:
            if ids[left] & ids[right]:
                raise CarlaRLPlanError(f"加载计划发现 split 泄漏: {left}/{right}")
            if hashes[left] & hashes[right]:
                raise CarlaRLPlanError(f"加载计划发现 scenario_hash 泄漏: {left}/{right}")
    if plan.get("leakage_check", {}).get("scenario_hash_overlap") != 0:
        raise CarlaRLPlanError("计划 leakage_check 未声明为零")
    return plan


class PlannedScenarioSampler:
    """Cycle through one frozen split without sampling another split."""

    def __init__(self, rows, *, seed):
        if not rows:
            raise CarlaRLPlanError("sampler 不能使用空 split")
        self.rows = copy.deepcopy(list(rows))
        self.seed = int(seed)
        self.rng = None
        self.order = []
        self.cursor = 0
        self.selection_count = 0
        self.selected = []
        self.selected_canonical_ids = set()
        self.selected_splits = set()

    def _rows_sha256(self):
        identity = [
            {
                "canonical_sample_id": row["canonical_sample_id"],
                "scenario_hash": row.get("scenario_hash"),
                "split": row["split"],
            }
            for row in self.rows
        ]
        return hashlib.sha256(_canonical_json(identity).encode("utf-8")).hexdigest()

    def _reset(self, seed):
        self.rng = np.random.default_rng(int(seed))
        self.order = self.rng.permutation(len(self.rows)).tolist()
        self.cursor = 0

    def __call__(self, seed=None, options=None):
        if seed is not None or self.rng is None:
            self._reset(self.seed if seed is None else int(seed))
        if self.cursor >= len(self.order):
            self._reset(int(self.rng.integers(0, 2**32 - 1)))
        row = self.rows[self.order[self.cursor]]
        self.cursor += 1
        self.selection_count += 1
        info = {
            "source": "carla_online_rl_multiscene_plan_v1",
            "plan_split": row["split"],
            "library_id": row["library_id"],
            "canonical_sample_id": row["canonical_sample_id"],
            "generator": row["generator"],
            "target_risk_level": row["target_risk_level"],
            "selection_index": self.selection_count - 1,
            "sampler_seed": self.seed,
        }
        self.selected.append(info)
        self.selected_canonical_ids.add(info["canonical_sample_id"])
        self.selected_splits.add(info["plan_split"])
        return copy.deepcopy(row["record"]), info

    def snapshot(self):
        return {
            "selection_count": self.selection_count,
            "unique_canonical_sample_id_count": len(self.selected_canonical_ids),
            "selected_splits": sorted(self.selected_splits),
            "cursor": self.cursor,
            "rows_sha256": self._rows_sha256(),
        }

    def state_dict(self):
        if self.rng is None:
            raise CarlaRLPlanError("sampler 尚未初始化，不能保存恢复状态")
        return {
            "format": SAMPLER_STATE_FORMAT,
            "seed": self.seed,
            "rows_sha256": self._rows_sha256(),
            "row_count": len(self.rows),
            "rng_state": copy.deepcopy(self.rng.bit_generator.state),
            "order": list(self.order),
            "cursor": self.cursor,
            "selection_count": self.selection_count,
            "selected_canonical_sample_ids": sorted(self.selected_canonical_ids),
            "selected_splits": sorted(self.selected_splits),
        }

    def load_state_dict(self, state):
        if not isinstance(state, dict) or state.get("format") != SAMPLER_STATE_FORMAT:
            raise CarlaRLPlanError("sampler 恢复状态格式不受支持")
        if int(state.get("seed", -1)) != self.seed:
            raise CarlaRLPlanError("sampler 恢复状态 seed 不一致")
        if (
            int(state.get("row_count", -1)) != len(self.rows)
            or state.get("rows_sha256") != self._rows_sha256()
        ):
            raise CarlaRLPlanError("sampler 恢复状态与当前 split 不一致")
        order = list(state.get("order") or [])
        if sorted(order) != list(range(len(self.rows))):
            raise CarlaRLPlanError("sampler 恢复状态 order 不是完整排列")
        cursor = int(state.get("cursor", -1))
        if cursor < 0 or cursor > len(order):
            raise CarlaRLPlanError("sampler 恢复状态 cursor 越界")
        selected_ids = set(state.get("selected_canonical_sample_ids") or [])
        valid_ids = {row["canonical_sample_id"] for row in self.rows}
        if not selected_ids.issubset(valid_ids):
            raise CarlaRLPlanError("sampler 恢复状态包含当前 split 之外的场景")
        rng = np.random.default_rng()
        try:
            rng.bit_generator.state = copy.deepcopy(state["rng_state"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CarlaRLPlanError("sampler RNG 状态无效") from exc
        self.rng = rng
        self.order = order
        self.cursor = cursor
        self.selection_count = int(state.get("selection_count", 0))
        if self.selection_count < 0:
            raise CarlaRLPlanError("sampler selection_count 不能为负数")
        self.selected = []
        self.selected_canonical_ids = selected_ids
        self.selected_splits = set(state.get("selected_splits") or [])
        valid_splits = {row["split"] for row in self.rows}
        if not self.selected_splits.issubset(valid_splits):
            raise CarlaRLPlanError("sampler 恢复状态包含当前 split 之外的标记")
        return self
