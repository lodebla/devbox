#!/usr/bin/env python3
"""Human-only SSH executor. Never mount /private in the agent container."""
import argparse
import getpass
import io
import json
import os
from pathlib import Path
import re
import resource
import shlex
import signal
import subprocess
import sys
import tempfile
import warnings

from common import read_json, request_id, shared_dirs, validate_request, write_json

OUTPUT_LIMIT = 256 * 1024


def terminal():
    # No getpass fallback to stdin: it could be an agent tool or a recorded pipe.
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError("A personal interactive terminal is required; never run approval through the agent")
    return io.TextIOWrapper(io.FileIO("/dev/tty", "r+"), line_buffering=True)


def private_dirs(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or not path.is_dir():
        raise ValueError("Private storage must be a real directory")
    os.chmod(path, 0o700)
    ledger = path / "ledger"
    ledger.mkdir(exist_ok=True, mode=0o700)
    if ledger.is_symlink() or not ledger.is_dir():
        raise ValueError("Private ledger must be a real directory")
    os.chmod(ledger, 0o700)
    return ledger


def connection(config, private, *, interactive=False):
    host, user, port = config["host"], config["user"], config["port"]
    if (not isinstance(host, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.:%_-]*", host)
            or not isinstance(user, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", user)
            or type(port) is not int or not 1 <= port <= 65535):
        raise ValueError("Invalid SSH host, account or port")
    options = [
        "-F", "/dev/null", "-p", str(port),
        "-o", "UserKnownHostsFile=" + str(private / "known_hosts"),
        "-o", "GlobalKnownHostsFile=/dev/null",
        "-o", "StrictHostKeyChecking=" + ("ask" if interactive else "yes"),
        "-o", "ForwardAgent=no", "-o", "ClearAllForwardings=yes",
        "-o", "IdentityAgent=none", "-o", "IdentitiesOnly=yes",
        "-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=2",
    ]
    if not interactive:
        options += ["-i", str(private / "id_ed25519"), "-o", "BatchMode=yes"]
    return options, user + "@" + host


def setup(args):
    with terminal() as tty:
        config = {"host": args.host, "user": args.user, "port": args.port}
        options, target = connection(config, args.private, interactive=True)
        private_dirs(args.private)
        if (args.private / "config.json").exists():
            tty.write("Replace existing SSH destination? Type REPLACE: ")
            if tty.readline().strip() != "REPLACE":
                raise ValueError("Setup cancelled")
        key = args.private / "id_ed25519"
        if not key.exists():
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "devbox-zima-admin", "-f", str(key)], check=True)
        tty.write("Verify the host fingerprint against ZimaOS before accepting it.\n"
                  "The following SSH password prompt is private; do not paste credentials into chat.\n")
        tty.flush()
        # ssh-copy-id creates temporary files under $HOME/.ssh. The container
        # root filesystem is read-only; keep its bootstrap workspace private too.
        (args.private / ".ssh").mkdir(exist_ok=True, mode=0o700)
        subprocess.run(
            ["ssh-copy-id", "-i", str(key) + ".pub", *options, target],
            env={**os.environ, "HOME": str(args.private)}, check=True,
        )
        batch, target = connection(config, args.private)
        subprocess.run(["ssh", "-T", *batch, target, "true"], stdin=subprocess.DEVNULL, check=True)
        write_json(args.private, "config.json", config)
        shared_dirs(args.exchange)
        print("SSH configured. Each request still requires human approval; sudo passwords are never saved.")


def claim(ledger, identifier, snapshot):
    # The exchange is attacker-writable. A private, exclusive record prevents replay
    # even if public request/result files are removed, replaced or forged.
    name = ledger / (identifier + ".json")
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump({"state": "claimed", "request": snapshot}, stream, ensure_ascii=True)
        stream.flush()
        os.fsync(stream.fileno())


def run_remote(config, private, request, password):
    options, target = connection(config, private)
    argv = request["argv"]
    if request["sudo"]:
        # Authenticate separately: NOPASSWD rules may leave the password unread.
        # Never allow the approved command to inherit that pipe (e.g. `cat`).
        # Both sudo invocations share a remote parent for non-TTY timestamp scope.
        # Invalidate before authentication and revoke again when the shell exits.
        command = (
            "trap 'sudo -k' 0; sudo -k && sudo -S -p '' -v && "
            "sudo -n -p '' -- " + shlex.join(argv) + " </dev/null"
        )
    else:
        command = "exec " + shlex.join(argv) + " </dev/null"
    # Capture command output in PRIVATE temporary files, never the terminal used
    # for authentication. Bounded child file size prevents unbounded RAM/disk use.
    def child_limits():
        resource.setrlimit(resource.RLIMIT_FSIZE, (OUTPUT_LIMIT, OUTPUT_LIMIT))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    with tempfile.TemporaryFile(dir=private) as stdout, tempfile.TemporaryFile(dir=private) as stderr:
        process = subprocess.Popen(
            ["ssh", "-T", *options, target, command], stdin=subprocess.PIPE,
            stdout=stdout, stderr=stderr, start_new_session=True, preexec_fn=child_limits,
        )
        try:
            process.communicate(password)
        except BaseException:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait()
            raise
        stdout.seek(0)
        stderr.seek(0)
        out = stdout.read(OUTPUT_LIMIT)
        err = stderr.read(OUTPUT_LIMIT)
        if len(out) == OUTPUT_LIMIT or len(err) == OUTPUT_LIMIT:
            err += b"\nOutput limit reached (256 KiB per stream); command may have been interrupted.\n"
        return process.returncode, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def approve(args):
    with terminal() as tty:
        identifier = request_id(args.id)
        ledger = private_dirs(args.private)
        requests, results = shared_dirs(args.exchange)
        request = validate_request(read_json(requests, identifier + ".json"))
        if request["id"] != identifier:
            raise ValueError("Request ID does not match its filename")
        if (ledger / (identifier + ".json")).exists():
            raise ValueError("Request already consumed; create a new request instead of replaying it")
        config = read_json(args.private, "config.json")
        connection(config, args.private)
        tty.write("\nDestination: " + json.dumps(config, ensure_ascii=True) + "\n")
        tty.write("Request: " + identifier + "\n")
        tty.write("sudo: " + str(request["sudo"]) + "\n")
        # JSON escaping prevents terminal control characters from hiding the command.
        tty.write("Exact argv: " + json.dumps(request["argv"], ensure_ascii=True) + "\n")
        tty.write("Command stdout/stderr will be shared with the agent. Do not approve secret-reading commands.\n")
        tty.write("Type APPROVE to execute this exact snapshot, or REJECT to deny: ")
        tty.flush()
        answer = tty.readline().strip()
        if answer not in ("APPROVE", "REJECT"):
            raise ValueError("Cancelled; request remains pending")
        claim(ledger, identifier, request)
        result = {"version": 1, "id": identifier, "status": "rejected", "exit_code": None, "stdout": "", "stderr": ""}
        try:
            if answer == "APPROVE":
                password = None
                if request["sudo"]:
                    # getpass normally falls back to echoed stdin if terminal
                    # controls fail. Fail closed instead of accepting that path.
                    with warnings.catch_warnings():
                        warnings.simplefilter("error", getpass.GetPassWarning)
                        password = (getpass.getpass("ZimaOS sudo password (not saved): ", stream=tty) + "\n").encode()
                try:
                    code, out, err = run_remote(config, args.private, request, password)
                finally:
                    password = None
                result.update(status="completed", exit_code=code, stdout=out, stderr=err)
        except getpass.GetPassWarning:
            result.update(status="interrupted", stderr="Cannot disable password echo; authentication refused without reading a password.")
        except (KeyboardInterrupt, OSError) as error:
            result.update(status="interrupted", stderr="Execution interrupted; check host state before submitting again.")
            if isinstance(error, OSError):
                result["stderr"] += " " + str(error)
        # Preserve authoritative result privately before exposing it to untrusted storage.
        write_json(ledger, identifier + ".json", {"request": request, "result": result})
        write_json(results, identifier + ".json", result)
        print("Result shared: " + identifier + " (" + result["status"] + ")")
        if result["exit_code"] not in (None, 0):
            return 1
        return 0 if result["status"] != "interrupted" else 1


def parser():
    value = argparse.ArgumentParser(description="Human-only ZimaOS executor; never run from agent tools")
    value.add_argument("--exchange", type=Path, default=Path("/exchange"))
    value.add_argument("--private", type=Path, default=Path("/private"))
    commands = value.add_subparsers(dest="action", required=True)
    commands.add_parser("init", help="Initialize private and shared storage (no network access)")
    configure = commands.add_parser("setup", help="Configure SSH interactively in a personal terminal")
    configure.add_argument("host")
    configure.add_argument("user")
    configure.add_argument("--port", type=int, default=22)
    approval = commands.add_parser("approve", help="Review and approve or reject exactly one request")
    approval.add_argument("id")
    return value


def main():
    args = parser().parse_args()
    # Password-bearing processes must not produce core dumps.
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.umask(0o077)
    try:
        if args.action == "init":
            private_dirs(args.private)
            shared_dirs(args.exchange)
            return 0
        if args.action == "setup":
            setup(args)
            return 0
        return approve(args)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print("zima-admin: " + str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("zima-admin: cancelled", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
