import unittest

import numpy as np

from core.mjx_multibody_probe import MultiBodyProbeConfig, surface_gap_m


class MJXMultiBodyGeometryTests(unittest.TestCase):
    def test_surface_gap_uses_relative_joint_offsets_once(self):
        config = MultiBodyProbeConfig(initial_gap_m=4.0, body_half_length_m=1.0)
        qpos = np.asarray([[0.0, 0.0], [0.5, -0.25]], dtype=np.float64)
        np.testing.assert_allclose(surface_gap_m(config, qpos), [4.0, 3.25])


if __name__ == "__main__":
    unittest.main()
