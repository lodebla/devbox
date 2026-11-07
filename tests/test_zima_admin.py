import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host-admin"))


class ZimaAdminSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.exchange = self.root / "exchange"
        self.private = self.root / "private"

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "host-admin/admin.py"),
             "--private", str(self.private), "--exchange", str(self.exchange), *args],
            input="", text=True, capture_output=True,
        )

    def test_shared_requests_cannot_follow_a_symlink_to_private_data(self):
        from common import read_json, shared_dirs
        requests, _ = shared_dirs(self.exchange)
        secret = self.root / "secret"
        secret.write_text('{"password":"must-not-be-read"}')
        (requests / "a.json").symlink_to(secret)
        with self.assertRaises((OSError, ValueError)):
            read_json(requests, "a.json")

    def test_shared_directory_cannot_redirect_writes_into_private_storage(self):
        from common import shared_dirs
        self.exchange.mkdir()
        self.private.mkdir()
        (self.exchange / "requests").symlink_to(self.private, target_is_directory=True)
        with self.assertRaises((OSError, ValueError)):
            shared_dirs(self.exchange)
        self.assertEqual(list(self.private.iterdir()), [])

    def test_request_validation_rejects_shell_command_strings_and_nonboolean_sudo(self):
        from common import validate_request
        base = {"version": 1, "id": "a" * 32, "argv": ["docker", "ps"], "sudo": True}
        for change in ({"argv": "docker ps"}, {"sudo": "false"}, {"argv": ["echo", "a\x00b"]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_request({**base, **change})

    def test_private_operations_refuse_piped_passwords_without_a_terminal(self):
        result = self.cli("setup", "127.0.0.1", "someone")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("terminal", result.stderr.lower())
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse((self.private / "id_ed25519").exists())

    def test_approval_without_terminal_never_consumes_or_executes_request(self):
        from common import shared_dirs, write_json
        requests, results = shared_dirs(self.exchange)
        identifier = "b" * 32
        write_json(requests, identifier + ".json", {
            "version": 1, "id": identifier, "argv": ["touch", str(self.root / "executed")], "sudo": True,
        })
        result = self.cli("approve", identifier)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("terminal", result.stderr.lower())
        self.assertFalse((self.root / "executed").exists())
        self.assertFalse((results / (identifier + ".json")).exists())
        self.assertFalse((self.private / "ledger" / (identifier + ".json")).exists())


if __name__ == "__main__":
    unittest.main()
