"""Untrusted exchange files shared by the agent and the human SSH executor."""
import json
import os
from pathlib import Path
import re
import stat
import uuid

MAX_JSON_BYTES = 4 * 1024 * 1024


def request_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise ValueError("Invalid request ID (expected 32 lowercase hexadecimal characters)")
    return value


def validate_request(value):
    if not isinstance(value, dict) or set(value) != {"version", "id", "argv", "sudo"}:
        raise ValueError("Invalid request fields")
    if type(value["version"]) is not int or value["version"] != 1:
        raise ValueError("Unsupported request version")
    request_id(value["id"])
    argv = value["argv"]
    if (not isinstance(argv, list) or not 1 <= len(argv) <= 256
            or any(not isinstance(arg, str) or "\x00" in arg or len(arg) > 16384 for arg in argv)
            or not argv[0] or argv[0].startswith("-")
            or sum(len(arg.encode("utf-8")) for arg in argv) > 65536):
        raise ValueError("Command must be an argv array without NUL bytes (maximum 64 KiB)")
    if type(value["sudo"]) is not bool:
        raise ValueError("sudo must be a boolean")
    return value


def _directory(path):
    return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)


def shared_dirs(exchange):
    exchange = Path(exchange)
    exchange.mkdir(parents=True, exist_ok=True)
    root = _directory(exchange)
    try:
        for name in ("requests", "results"):
            try:
                os.mkdir(name, 0o777, dir_fd=root)
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
                try:
                    os.fchmod(child, 0o777)
                finally:
                    os.close(child)
            except FileExistsError:
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
                os.close(child)
    finally:
        os.close(root)
    return exchange / "requests", exchange / "results"


def read_json(directory, name):
    if Path(name).name != name or name in (".", ".."):
        raise ValueError("Invalid exchange filename")
    parent = _directory(directory)
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_JSON_BYTES:
                raise ValueError("Exchange entry must be a regular JSON file of at most 4 MiB")
            raw = stream.read(MAX_JSON_BYTES + 1)
            if len(raw) > MAX_JSON_BYTES:
                raise ValueError("Exchange JSON exceeds 4 MiB")
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("Expected a JSON object")
            return value
    finally:
        os.close(parent)


def write_json(directory, name, value):
    if Path(name).name != name or name in (".", ".."):
        raise ValueError("Invalid exchange filename")
    raw = (json.dumps(value, ensure_ascii=True, allow_nan=False) + "\n").encode()
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("Exchange JSON exceeds 4 MiB")
    parent = _directory(directory)
    temporary = "." + uuid.uuid4().hex + ".tmp"
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=parent)
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o644)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
    finally:
        try:
            os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError:
            pass
        os.close(parent)
