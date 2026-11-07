#!/usr/bin/env python3
"""Real localhost SSH/sudo security smoke. Run as root; creates/removes one test user."""
import json
import os
from pathlib import Path
import pty
import select
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import termios
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host-admin"))
from common import read_json, shared_dirs, write_json


def run(argv, **kwargs):
    return subprocess.run(argv, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)


def interact(argv, steps, mutate=None):
    pid, fd = pty.fork()
    if pid == 0:
        os.execv(argv[0], argv)
    transcript = bytearray()
    step = 0
    deadline = time.monotonic() + 30
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([fd], [], [], 0.2)
            if ready:
                try:
                    chunk = os.read(fd, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                transcript.extend(chunk)
            if step < len(steps) and steps[step][0].encode() in transcript:
                prompt, response, secret = steps[step]
                if secret:
                    assert not termios.tcgetattr(fd)[3] & termios.ECHO, "Password terminal echo is enabled"
                if mutate and step == 0:
                    mutate()
                os.write(fd, response.encode() + b"\n")
                step += 1
        else:
            raise AssertionError("Interactive command timed out: " + transcript.decode(errors="replace"))
        _, status = os.waitpid(pid, 0)
        assert step == len(steps), transcript.decode(errors="replace")
        return os.waitstatus_to_exitcode(status), bytes(transcript)
    finally:
        os.close(fd)
        try:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
        except (ProcessLookupError, ChildProcessError):
            pass


def main():
    if os.geteuid() != 0:
        raise SystemExit("Run with sudo python3 tests/smoke_zima_admin.py")
    for name in ("sshd", "ssh", "ssh-keygen", "useradd", "userdel", "chpasswd", "visudo"):
        if not shutil.which(name):
            raise SystemExit("Missing smoke prerequisite: " + name)
    username = "zsm" + uuid.uuid4().hex[:10]
    secret = "Only-fixture-" + uuid.uuid4().hex
    sudoers = Path("/etc/sudoers.d") / username
    daemon = None
    created = False
    with tempfile.TemporaryDirectory(prefix="zima-smoke-") as temp:
        base = Path(temp)
        os.chmod(base, 0o755)
        private = base / "private"
        private.mkdir(mode=0o700)
        exchange = base / "exchange"
        requests, results = shared_dirs(exchange)
        try:
            run(["useradd", "-M", "-d", str(base / "home"), "-s", "/bin/sh", username])
            created = True
            run(["chpasswd"], input=(username + ":" + secret + "\n").encode())
            home = base / "home"
            home.mkdir(mode=0o700)
            import pwd
            account = pwd.getpwnam(username)
            os.chown(home, account.pw_uid, account.pw_gid)
            for path in (private / "id_ed25519", base / "host_key"):
                run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(path)])
            authorized = base / "authorized_keys"
            authorized.write_bytes((private / "id_ed25519.pub").read_bytes())
            os.chmod(authorized, 0o644)
            with socket.socket() as reserved:
                reserved.bind(("127.0.0.1", 0))
                port = reserved.getsockname()[1]
            config = base / "sshd_config"
            config.write_text(
                f"Port {port}\nListenAddress 127.0.0.1\nHostKey {base / 'host_key'}\n"
                f"PidFile {base / 'sshd.pid'}\nAuthorizedKeysFile {authorized} .ssh/authorized_keys\n"
                f"AllowUsers {username}\nPasswordAuthentication yes\nKbdInteractiveAuthentication no\n"
                "UsePAM no\nStrictModes no\nPermitRootLogin no\nLogLevel ERROR\n"
            )
            Path("/run/sshd").mkdir(exist_ok=True)
            daemon = subprocess.Popen([shutil.which("sshd"), "-D", "-e", "-f", str(config)], stderr=subprocess.PIPE)
            deadline = time.monotonic() + 10
            while True:
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    if daemon.poll() is not None or time.monotonic() > deadline:
                        daemon.terminate()
                        daemon.wait(timeout=10)
                        raise AssertionError("sshd failed: " + daemon.stderr.read().decode())
                    time.sleep(0.05)
            (private / "known_hosts").write_text(f"[127.0.0.1]:{port} " + (base / "host_key.pub").read_text())
            write_json(private, "config.json", {"host": "127.0.0.1", "user": username, "port": port})
            command = [sys.executable, str(ROOT / "host-admin/admin.py"), "--private", str(private), "--exchange", str(exchange)]
            setup_private = base / "setup-private"
            setup_command = [sys.executable, str(ROOT / "host-admin/admin.py"),
                             "--private", str(setup_private), "--exchange", str(exchange),
                             "setup", "127.0.0.1", username, "--port", str(port)]
            status, transcript = interact(setup_command, [
                ("Are you sure you want to continue connecting", "yes", False),
                (username + "@127.0.0.1's password:", secret, True),
            ])
            assert status == 0 and secret.encode() not in transcript, transcript.decode(errors="replace")
            assert read_json(setup_private, "config.json")["user"] == username
            for file in setup_private.rglob("*"):
                if file.is_file():
                    assert secret.encode() not in file.read_bytes(), "Setup password persisted"
            print("PASS: interactive SSH setup verifies host identity and installs an isolated key")

            def policy(nopasswd=False):
                sudoers.write_text(
                    f"Defaults:{username} !requiretty, timestamp_type=ppid, passwd_tries=1, lecture=never\n"
                    f"{username} ALL=(root) {'NOPASSWD' if nopasswd else 'PASSWD'}: /usr/bin/id, /usr/bin/printf, /usr/bin/cat, /usr/bin/touch\n"
                )
                os.chmod(sudoers, 0o440)
                run(["visudo", "-cf", str(sudoers)])

            client = [sys.executable, str(ROOT / "host-admin/client.py"), "--exchange", str(exchange)]
            def request(argv, sudo=True):
                output = run(client + ["request"] + (["--sudo"] if sudo else []) + ["--", *argv])
                return output.stdout.decode().strip()

            def approve(identifier, password=secret, mutate=None):
                status, transcript = interact(command + ["approve", identifier], [
                    ("Type APPROVE", "APPROVE", False),
                    ("ZimaOS sudo password (not saved): ", password, True),
                ], mutate)
                assert secret.encode() not in transcript, "Password leaked to terminal output"
                for file in exchange.rglob("*.json"):
                    assert secret.encode() not in file.read_bytes(), "Password leaked into exchange"
                for file in private.rglob("*"):
                    if file.is_file():
                        assert secret.encode() not in file.read_bytes(), "Password persisted in private storage"
                return status, json.loads(run(client + ["result", identifier]).stdout)

            policy()
            identifier = request(["/usr/bin/id", "-u"])
            status, result = approve(identifier)
            assert status == 0 and result["exit_code"] == 0 and result["stdout"] == "0\n", result
            print("PASS: real SSH + password-required sudo executes approved command as root")

            altered = request(["/usr/bin/printf", "%s", "original; $(touch /not-executed)"])
            def replace_request():
                write_json(requests, altered + ".json", {"version": 1, "id": altered, "argv": ["/usr/bin/printf", "tampered"], "sudo": True})
            status, result = approve(altered, mutate=replace_request)
            assert status == 0 and result["stdout"] == "original; $(touch /not-executed)", result
            print("PASS: approval uses immutable displayed snapshot and preserves shell metacharacters")

            status, transcript = interact(command + ["approve", identifier], [])
            assert status != 0 and b"already consumed" in transcript, transcript
            print("PASS: private ledger blocks replay even if requests are still present")

            marker = base / "wrong-password-command"
            failed = request(["/usr/bin/touch", str(marker)])
            status, result = approve(failed, password="wrong-fixture-password")
            assert status != 0 and result["exit_code"] != 0 and not marker.exists(), result
            print("PASS: wrong sudo password does not execute command")

            policy(nopasswd=True)
            no_password = request(["/usr/bin/cat"])
            status, result = approve(no_password)
            assert status == 0 and result["stdout"] == "", result
            print("PASS: NOPASSWD cannot leak unread password through command stdin")

            plain = request(["/usr/bin/id", "-un"], sudo=False)
            status, transcript = interact(command + ["approve", plain], [("Type APPROVE", "APPROVE", False)])
            result = json.loads(run(client + ["result", plain]).stdout)
            assert status == 0 and result["stdout"] == username + "\n", result
            assert b"sudo password" not in transcript
            print("PASS: unprivileged requests run as the SSH account without a sudo password")

            trusted = (private / "known_hosts").read_bytes()
            (private / "known_hosts").write_text(f"[127.0.0.1]:{port} " + (private / "id_ed25519.pub").read_text())
            untrusted = request(["/usr/bin/touch", str(base / "untrusted-host-command")])
            status, result = approve(untrusted)
            assert status != 0 and result["exit_code"] == 255, result
            assert not (base / "untrusted-host-command").exists()
            assert "HOST IDENTIFICATION HAS CHANGED" in result["stderr"], result
            (private / "known_hosts").write_bytes(trusted)
            print("PASS: changed SSH host identity blocks execution instead of accepting a new key")

            denied = request(["/usr/bin/touch", str(base / "denied-command")])
            status, transcript = interact(command + ["approve", denied], [("Type APPROVE", "REJECT", False)])
            assert status == 0 and read_json(results, denied + ".json")["status"] == "rejected"
            assert not (base / "denied-command").exists()
            print("PASS: rejection never authenticates or executes")
        finally:
            if daemon is not None:
                daemon.terminate()
                daemon.wait(timeout=10)
                daemon.stderr.close()
            sudoers.unlink(missing_ok=True)
            if created:
                run(["userdel", username])
    print("PASS: temporary SSH server, account, sudo policy and files cleaned up")


if __name__ == "__main__":
    main()
