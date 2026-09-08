from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


class InstallerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.script = Path(__file__).parents[1] / "scripts" / "install-service.sh"
        self.source = self.script.read_text(encoding="utf-8")

    def test_installer_is_syntactically_valid_and_does_not_source_env(self) -> None:
        result = subprocess.run(["bash", "-n", str(self.script)], check=False, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('. "$ENV_FILE"', self.source)
        self.assertIn("read_env_value()", self.source)
        self.assertIn("read_env_value HIERARCHY_TOKEN", self.source)
        self.assertIn("Never execute an environment file as root", self.source)

    def test_service_identity_and_codex_contract_are_explicit(self) -> None:
        for fragment in (
            'SERVICE_USER="${HIERARCHY_SERVICE_USER:-${EXISTING_SERVICE_USER:-${SUDO_USER:-}}}"',
            'EXISTING_SERVICE_USER',
            'EXISTING_CHATGPT_BACKEND',
            'EXISTING_CODEX_BIN',
            'EXISTING_CODEX_HOME',
            'User=$SERVICE_USER',
            'Group=$SERVICE_GROUP',
            'Environment=HOME=$SERVICE_HOME',
            'set_env_line HIERARCHY_CHATGPT_BACKEND',
            ':-auto',
            'HIERARCHY_CODEX_BIN',
            'HIERARCHY_CODEX_HOME',
            'runuser -u "$SERVICE_USER"',
        ):
            self.assertIn(fragment, self.source)

    def test_install_reloads_enables_and_restarts_updated_service(self) -> None:
        self.assertIn("systemctl daemon-reload", self.source)
        self.assertIn("systemctl enable hierarchy.service", self.source)
        self.assertIn("if ! systemctl restart hierarchy.service; then", self.source)
        self.assertIn(
            'failed to restart hierarchy.service after installing the updated service configuration',
            self.source,
        )
        self.assertLess(
            self.source.index("systemctl daemon-reload"),
            self.source.index("systemctl enable hierarchy.service"),
        )
        self.assertLess(
            self.source.index("systemctl enable hierarchy.service"),
            self.source.index("systemctl restart hierarchy.service"),
        )


if __name__ == "__main__":
    unittest.main()
