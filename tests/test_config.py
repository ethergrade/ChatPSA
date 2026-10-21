from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chatpsa.config import Settings


class SettingsTests(unittest.TestCase):
    def test_explicit_env_path_loads_without_using_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / "custom.env"
            env_file.write_text(
                "HALO_BASE_URL=https://example.invalid/\n"
                "HALO_CLIENT_ID=test-id\n"
                "HALO_CLIENT_SECRET=test-secret\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                settings = Settings.from_env(env_file)

        self.assertEqual(settings.base_url, "https://example.invalid")
        self.assertFalse(settings.enable_writes)
        self.assertNotIn("test-secret", repr(settings))

    def test_process_environment_takes_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / "custom.env"
            env_file.write_text(
                "HALO_BASE_URL=https://file.invalid\n"
                "HALO_CLIENT_ID=file-id\n"
                "HALO_CLIENT_SECRET=file-secret\n",
                encoding="utf-8",
            )
            process_env = {
                "HALO_BASE_URL": "https://process.invalid",
                "HALO_CLIENT_ID": "process-id",
                "HALO_CLIENT_SECRET": "process-secret",
            }
            with patch.dict(os.environ, process_env, clear=True):
                settings = Settings.from_env(env_file)

        self.assertEqual(settings.base_url, "https://process.invalid")
        self.assertEqual(settings.client_id, "process-id")


if __name__ == "__main__":
    unittest.main()
