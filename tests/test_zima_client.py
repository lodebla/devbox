import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host-admin"))

from common import read_json, shared_dirs, write_json


class ZimaHostClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.exchange = self.root / "exchange"

    def cli(self, *args, exchange=None):
        command = [str(ROOT / "bin/zima-host")]
        if exchange is not None:
            command.extend(("--exchange", str(exchange)))
        environment = os.environ.copy()
        environment["ZIMA_EXCHANGE_DIR"] = str(self.exchange)
        return subprocess.run(command + list(args), text=True, capture_output=True, env=environment)

    def submit(self, *command, sudo=False):
        args = ["request"]
        if sudo:
            args.append("--sudo")
        args.extend(("--", *command))
        result = self.cli(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        identifier = result.stdout.strip()
        self.assertRegex(identifier, r"^[0-9a-f]{32}$")
        return identifier

    def add_result(self, identifier, status, *, exit_code=None, stdout="", stderr=""):
        _, results = shared_dirs(self.exchange)
        write_json(results, identifier + ".json", {
            "version": 1,
            "id": identifier,
            "status": status,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
        })

    def test_request_preserves_argv_and_never_runs_the_command(self):
        marker = self.root / "must-not-exist"
        script = f"touch -- {shlex.quote(str(marker))}; printf '%s' '$HOME; && *'"
        identifier = self.submit("sh", "-c", script, sudo=True)

        requests, _ = shared_dirs(self.exchange)
        request = read_json(requests, identifier + ".json")
        self.assertEqual(request, {
            "version": 1,
            "id": identifier,
            "argv": ["sh", "-c", script],
            "sudo": True,
        })
        self.assertFalse(marker.exists(), "request creation must not execute its argv")

    def test_list_and_result_report_pending_completed_and_rejected(self):
        completed_id = self.submit("printf", "%s", "safe")

        pending_result = self.cli("result", completed_id)
        self.assertNotEqual(pending_result.returncode, 0)
        self.assertIn("pending", pending_result.stderr)
        self.assertNotIn("Traceback", pending_result.stderr)
        listing = self.cli("list")
        self.assertEqual(listing.returncode, 0, listing.stderr)
        self.assertIn(f"{completed_id} pending", listing.stdout)

        completed = {
            "version": 1,
            "id": completed_id,
            "status": "completed",
            "exit_code": 0,
            "stdout": "safe",
            "stderr": "",
        }
        self.add_result(completed_id, "completed", exit_code=0, stdout="safe")
        output = self.cli("result", completed_id)
        self.assertEqual(output.returncode, 0, output.stderr)
        self.assertEqual(json.loads(output.stdout), completed)
        listing = self.cli("list")
        self.assertIn(f"{completed_id} completed", listing.stdout)

        rejected_id = self.submit("false")
        self.add_result(rejected_id, "rejected", stderr="approval denied")
        rejected = self.cli("result", rejected_id)
        self.assertEqual(rejected.returncode, 0, rejected.stderr)
        self.assertEqual(json.loads(rejected.stdout)["status"], "rejected")
        listing = self.cli("list")
        self.assertIn(f"{rejected_id} rejected", listing.stdout)

    def test_invalid_ids_are_rejected_without_traversing_exchange(self):
        shared_dirs(self.exchange)
        outside_exchange = self.exchange / "outside.json"
        outside_exchange.write_text(json.dumps({
            "version": 1,
            "id": "c" * 32,
            "status": "completed",
            "exit_code": 0,
            "stdout": "must not be read",
            "stderr": "",
        }), encoding="utf-8")

        for identifier in ("../outside", "A" * 32, "short"):
            with self.subTest(identifier=identifier):
                result = self.cli("result", identifier)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("must not be read", result.stdout)
                self.assertNotIn("Traceback", result.stderr)
        self.assertTrue(outside_exchange.is_file())

    def test_malformed_requests_are_rejected_before_creating_exchange_files(self):
        invalid_requests = (
            ("request",),
            ("request", "echo", "missing-delimiter"),
            ("request", "--", "--invalid-command"),
        )
        for args in invalid_requests:
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse(self.exchange.exists())

    def test_explicit_exchange_directory_overrides_environment(self):
        alternate = self.root / "alternate exchange"
        result = self.cli("request", "--", "printf", "alternate", exchange=alternate)
        self.assertEqual(result.returncode, 0, result.stderr)
        identifier = result.stdout.strip()
        requests, _ = shared_dirs(alternate)
        self.assertEqual(read_json(requests, identifier + ".json")["argv"], ["printf", "alternate"])
        self.assertFalse(self.exchange.exists())


if __name__ == "__main__":
    unittest.main()
