"""Export a small, offline road preview using CARLA's OpenDRIVE parser."""

import argparse
from collections import defaultdict
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path


def export_map(source, output, spacing=2.0):
    import carla

    carla_version = version("carla")
    if carla_version != "0.9.16":
        raise ValueError("Preview assets require CARLA 0.9.16")
    raw = source.read_bytes()
    road_map = carla.Map(source.stem, raw.decode("utf-8"))
    groups = defaultdict(dict)
    waypoints = road_map.generate_waypoints(spacing)
    for endpoints in road_map.get_topology():
        waypoints.extend(endpoints)
    for point in waypoints:
        key = (point.road_id, point.section_id, point.lane_id)
        groups[key][round(point.s, 4)] = point
    lanes = []
    for key, points in sorted(groups.items()):
        ordered = sorted(points.values(), key=lambda point: point.s, reverse=key[2] > 0)
        if len(ordered) < 2:
            continue
        lanes.append({
            "road_id": key[0],
            "lane_id": key[2],
            "junction": ordered[0].is_junction,
            "points": [[
                round(point.transform.location.x, 3),
                round(point.transform.location.y, 3),
                round(point.transform.location.z, 3),
                round(point.transform.rotation.yaw, 3),
                round(point.lane_width, 3),
            ] for point in ordered],
        })
    def length(lane):
        return sum(math.hypot(b[0] - a[0], b[1] - a[1])
                   for a, b in zip(lane["points"], lane["points"][1:]))

    example = max((lane for lane in lanes if not lane["junction"]), key=length)
    points = example["points"]
    start = max(1, len(points) // 4)
    origin = points[start][:3]
    result = {
        "source": {
            "map": source.stem,
            "carla_version": carla_version,
            "opendrive_sha256": hashlib.sha256(raw).hexdigest(),
            "sample_spacing_m": spacing,
        },
        "origin": origin,
        "example_route": points[start:],
        "lanes": lanes,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Exported {len(lanes)} lanes; example road {example['road_id']}; {output.stat().st_size} bytes")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "web_assets" / "town10hd.json")
    args = parser.parse_args()
    export_map(args.source, args.output)


if __name__ == "__main__":
    main()
