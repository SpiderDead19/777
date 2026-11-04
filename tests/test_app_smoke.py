"""Smoke check for the Streamlit interface in packaged/local mode."""
import os
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


class AppSmokeTests(unittest.TestCase):
    def test_local_app_starts_without_password(self):
        previous = os.environ.get("SNAB_LOCAL_MODE")
        os.environ["SNAB_LOCAL_MODE"] = "1"
        try:
            app = AppTest.from_file(Path(__file__).resolve().parents[1] / "online_app.py")
            app.run(timeout=20)
            self.assertFalse(app.exception)
            self.assertTrue(any("ИИ-Снабженец 3.0" in title.value for title in app.title))
        finally:
            if previous is None:
                os.environ.pop("SNAB_LOCAL_MODE", None)
            else:
                os.environ["SNAB_LOCAL_MODE"] = previous


if __name__ == "__main__":
    unittest.main()
