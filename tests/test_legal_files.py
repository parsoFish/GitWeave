"""Tests for repo legal files — LICENSE and CLA.md.

AC1: LICENSE is AGPL-3.0-or-later verbatim (includes 'or later' notice);
     CLA.md is Apache ICLA standard form.
"""

import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestLegalFiles(unittest.TestCase):

    # --- LICENSE ---

    def test_license_file_exists(self):
        path = os.path.join(REPO_ROOT, "LICENSE")
        self.assertTrue(os.path.isfile(path), "LICENSE file is missing")

    def test_license_is_agpl3(self):
        path = os.path.join(REPO_ROOT, "LICENSE")
        content = open(path).read()
        self.assertIn(
            "GNU AFFERO GENERAL PUBLIC LICENSE",
            content,
            "LICENSE does not contain 'GNU AFFERO GENERAL PUBLIC LICENSE'",
        )
        self.assertIn(
            "Version 3",
            content,
            "LICENSE does not declare Version 3",
        )

    def test_license_contains_or_later_notice(self):
        """AGPL-3.0-or-later: the 'or later' option must be present in the file."""
        import re

        path = os.path.join(REPO_ROOT, "LICENSE")
        content = open(path).read()
        # Normalize whitespace so the phrase is detectable even when line-wrapped
        normalized = re.sub(r"\s+", " ", content)
        self.assertIn(
            "or (at your option) any later version",
            normalized,
            "LICENSE missing 'or later' notice required for AGPL-3.0-or-later",
        )

    # --- CLA.md ---

    def test_cla_file_exists(self):
        path = os.path.join(REPO_ROOT, "CLA.md")
        self.assertTrue(os.path.isfile(path), "CLA.md file is missing")

    def test_cla_is_apache_icla(self):
        path = os.path.join(REPO_ROOT, "CLA.md")
        content = open(path).read()
        self.assertIn(
            "Individual Contributor License Agreement",
            content,
            "CLA.md does not contain 'Individual Contributor License Agreement'",
        )

    def test_cla_contains_apache_copyright_grant(self):
        path = os.path.join(REPO_ROOT, "CLA.md")
        content = open(path).read()
        self.assertIn(
            "copyright license",
            content.lower(),
            "CLA.md missing copyright license grant",
        )
        self.assertIn(
            "patent license",
            content.lower(),
            "CLA.md missing patent license grant",
        )

    def test_cla_verbatim_asf_icla_passage(self):
        """CLA.md must be the verbatim ASF ICLA v2.0 text (project name substituted).

        Checks a distinctive verbatim passage that only appears in the canonical
        ASF ICLA v2.0 text and would be absent from a restructured paraphrase.
        """
        path = os.path.join(REPO_ROOT, "CLA.md")
        import re
        content = open(path).read()
        # Normalise whitespace so line-wrap differences don't cause false failures
        normalized = re.sub(r"\s+", " ", content)
        # Verbatim passage from ASF ICLA v2.0 §1 (with "Foundation" → "GitWeave")
        self.assertIn(
            'intentionally submitted by You to GitWeave for inclusion in, '
            'or documentation of, any of the products owned or managed by GitWeave',
            normalized,
            "CLA.md is missing the verbatim ASF ICLA v2.0 §1 Contribution definition "
            "(with 'The Apache Software Foundation' replaced by 'GitWeave'). "
            "The file must be the verbatim ASF ICLA v2.0 text, not a restructured paraphrase.",
        )
        # Verbatim passage from ASF ICLA v2.0 preamble
        self.assertIn(
            'You accept and agree to the following terms and conditions for '
            'Your present and future Contributions submitted to GitWeave.',
            normalized,
            "CLA.md is missing the verbatim ASF ICLA v2.0 preamble acceptance clause "
            "(with 'The Apache Software Foundation' replaced by 'GitWeave').",
        )


if __name__ == "__main__":
    unittest.main()
