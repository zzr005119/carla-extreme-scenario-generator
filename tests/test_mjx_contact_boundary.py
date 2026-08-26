import unittest

from tools.scan_mjx_multibody_contact_boundary import (
    CONTACT_BOUNDARY_DESIGN,
    classify_case,
)


class MJXContactBoundaryTests(unittest.TestCase):
    def test_design_is_independent_counter_motion(self):
        self.assertEqual(len(CONTACT_BOUNDARY_DESIGN), 6)
        self.assertTrue(all(row["ego_force"] > 0 for row in CONTACT_BOUNDARY_DESIGN))
        self.assertTrue(all(row["lead_force"] < 0 for row in CONTACT_BOUNDARY_DESIGN))
        self.assertEqual(
            {row["ego_force"] + abs(row["lead_force"]) for row in CONTACT_BOUNDARY_DESIGN},
            {0.5, 1.0, 2.0, 3.0, 4.0, 6.0},
        )

    def test_classification_separates_numerical_and_contact_gates(self):
        self.assertEqual(
            classify_case(
                finite=True,
                finite_difference_error=1e-6,
                native_aligned=True,
                contact_observed=False,
                penetration_m=0.0,
                penetration_tolerance_m=0.05,
            )[0],
            "no_contact_stable",
        )
        self.assertEqual(
            classify_case(
                finite=True,
                finite_difference_error=1e-6,
                native_aligned=True,
                contact_observed=True,
                penetration_m=0.01,
                penetration_tolerance_m=0.05,
            )[0],
            "contact_stable",
        )
        self.assertEqual(
            classify_case(
                finite=True,
                finite_difference_error=1e-6,
                native_aligned=True,
                contact_observed=True,
                penetration_m=0.2,
                penetration_tolerance_m=0.05,
            )[0],
            "contact_penetration_unstable",
        )
        self.assertEqual(
            classify_case(
                finite=False,
                finite_difference_error=1.0,
                native_aligned=False,
                contact_observed=True,
                penetration_m=0.0,
                penetration_tolerance_m=0.05,
            )[0],
            "numerical_failure",
        )


if __name__ == "__main__":
    unittest.main()
