# Offline Design Preview

The generation page loads these assets locally. It does not request a map API,
connect to CARLA, submit a task, or estimate observed risk when controls change.

- `town10hd.json`: road centerlines and lane widths extracted from the CARLA
  0.9.16 `Town10HD_Opt.xodr` distributed with the local CARLA installation.
  The source SHA-256 and sampling interval are stored inside the asset.
  Rendering flattens elevation; buildings and roadside meshes are not exported.
- `example_route`: a fixed illustrative lane, not the generated candidate's
  route or a runtime trajectory. Vehicle and pedestrian placements are examples.
- Weather checkboxes write the existing `weather_tags` field. Unknown or
  conflicting tags remain visible for correction. A target risk selection only
  changes the design label, never the geometry or an observed risk score.
- Renderer and data loading failures display a retry action without preventing
  the generation form from submitting. Offscreen and hidden tabs pause drawing;
  reduced-motion preferences stop the weather animation.

Regenerate the geometry with the project CARLA 0.9.16 environment (no simulator
server is required):

```powershell
& 'D:\ANACONDA\envs\Carla666-0916\python.exe' tools/export_design_preview_map.py 'F:\Carla\carla-0.9.16\CarlaUE4\Content\Carla\Maps\OpenDrive\Town10HD_Opt.xodr'
```

## Third-party Sources

The checked-in vendor files are pinned, with only three whitespace fixes in the
JavaScript sources. Browsers do not contact these download hosts at runtime.

| Files | Version | Source | License |
| --- | --- | --- | --- |
| `three.module.js`, `OrbitControls.js` | Three.js 0.160.1 | https://github.com/mrdoob/three.js/tree/r160 | `vendor/THREE-LICENSE.txt` (MIT) |
| `rotate-ccw.svg` | lucide-static 0.468.0 | https://github.com/lucide-icons/lucide/tree/0.468.0 | `vendor/LUCIDE-LICENSE.txt` (ISC; Feather portions MIT) |
| `town10hd.json` (derived road geometry) | CARLA 0.9.16 | https://github.com/carla-simulator/carla | `vendor/CARLA-LICENSE.txt`; CARLA additional assets attribution below |

CARLA authors: Computer Vision Center (CVC), Universitat Autonoma de Barcelona
(UAB), and contributors. CARLA code is MIT licensed; CARLA-specific assets are
CC-BY licensed, as stated in https://github.com/carla-simulator/carla/blob/0.9.16/README.md.
The road geometry has been resampled and reduced to lane information for this
design preview; it is not a redistribution of the complete CARLA map.

Downloads used for the pinned vendor files:

- https://cdn.jsdelivr.net/npm/three@0.160.1/build/three.module.js
- https://cdn.jsdelivr.net/npm/three@0.160.1/examples/jsm/controls/OrbitControls.js
- https://cdn.jsdelivr.net/npm/lucide-static@0.468.0/icons/rotate-ccw.svg
