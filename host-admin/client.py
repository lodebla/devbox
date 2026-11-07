#!/usr/bin/env python3
"""Submit and inspect host-admin requests without executing them locally."""
import argparse
import json
import os
from pathlib import Path
import sys
import uuid

from common import read_json, request_id, shared_dirs, validate_request, write_json


DEFAULT_EXCHANGE = "/zima-exchange"
_RESULT_FIELDS = {"version", "id", "status", "exit_code", "stdout", "stderr"}
_RESULT_STATUSES = {"completed", "rejected", "interrupted"}


class ClientError(ValueError):
    """An expected, user-correctable CLI or exchange error."""


def _parser():
    parser = argparse.ArgumentParser(prog="zima-host")
    parser.add_argument(
        "--exchange",
        default=os.environ.get("ZIMA_EXCHANGE_DIR", DEFAULT_EXCHANGE),
        metavar="DIR",
        help="shared exchange directory (default: ZIMA_EXCHANGE_DIR or /zima-exchange)",
    )
    commands = parser.add_subparsers(dest="action", required=True)

    request_parser = commands.add_parser("request", help="submit a command for human approval")
    request_parser.add_argument("--sudo", action="store_true", help="request sudo for the approved command")
    request_parser.add_argument("command", nargs=argparse.REMAINDER, metavar="-- COMMAND [ARGS...]")

    commands.add_parser("list", help="list pending and completed requests")

    result_parser = commands.add_parser("result", help="print the result for a request")
    result_parser.add_argument("id", metavar="ID")
    return parser, request_parser


def _has_request_separator(argv):
    """Require the explicit delimiter separating client options from argv."""
    index = 0
    while index < len(argv):
        value = argv[index]
        if value == "--exchange":
            index += 2
            continue
        if value.startswith("--exchange="):
            index += 1
            continue
        if value == "request":
            index += 1
            while index < len(argv) and argv[index] == "--sudo":
                index += 1
            return index < len(argv) and argv[index] == "--"
        # Let argparse report unknown options or an invalid subcommand.
        return True
    return True


def _request(exchange, command, sudo):
    request = {
        "version": 1,
        "id": uuid.uuid4().hex,
        "argv": command,
        "sudo": sudo,
    }
    # Validate before creating the shared directories: malformed requests have
    # no side effects and never enter the approval queue.
    validate_request(request)
    requests, _ = shared_dirs(exchange)
    write_json(requests, request["id"] + ".json", request)
    print(request["id"])
    return 0


def _request_file(requests, identifier):
    request = validate_request(read_json(requests, identifier + ".json"))
    if request["id"] != identifier:
        raise ClientError("request ID does not match its exchange filename")
    return request


def _validate_result(result, identifier):
    if not isinstance(result, dict) or set(result) != _RESULT_FIELDS:
        raise ClientError("invalid result fields")
    if type(result["version"]) is not int or result["version"] != 1:
        raise ClientError("unsupported result version")
    if result["id"] != identifier:
        raise ClientError("result ID does not match its exchange filename")
    if not isinstance(result["status"], str) or result["status"] not in _RESULT_STATUSES:
        raise ClientError("invalid result status")
    if result["exit_code"] is not None and type(result["exit_code"]) is not int:
        raise ClientError("invalid result exit code")
    if not isinstance(result["stdout"], str) or not isinstance(result["stderr"], str):
        raise ClientError("invalid result output")
    return result


def _result(exchange, supplied_id):
    identifier = request_id(supplied_id)
    requests, results = shared_dirs(exchange)
    try:
        result = read_json(results, identifier + ".json")
    except FileNotFoundError:
        try:
            _request_file(requests, identifier)
        except FileNotFoundError:
            raise ClientError(f"request {identifier} not found") from None
        raise ClientError(f"request {identifier} is pending") from None
    _validate_result(result, identifier)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _exchange_ids(directory):
    identifiers = set()
    for entry in directory.iterdir():
        if not entry.name.endswith(".json"):
            continue
        candidate = entry.name[:-5]
        try:
            identifiers.add(request_id(candidate))
        except ValueError:
            # Do not interpret arbitrary exchange filenames as request paths.
            continue
    return identifiers


def _list(exchange):
    requests, results = shared_dirs(exchange)
    statuses = []
    for identifier in sorted(_exchange_ids(requests)):
        try:
            _request_file(requests, identifier)
        except FileNotFoundError:
            continue
        except (OSError, ValueError):
            statuses.append((identifier, "rejected"))
            continue

        try:
            result = read_json(results, identifier + ".json")
        except FileNotFoundError:
            status = "pending"
        except (OSError, ValueError):
            status = "rejected"
        else:
            try:
                status = _validate_result(result, identifier)["status"]
            except ValueError:
                status = "rejected"
        statuses.append((identifier, status))

    if not statuses:
        print("No requests.")
        return 0
    for identifier, status in statuses:
        print(f"{identifier} {status}")
    return 0


def main(argv=None):
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    parser, request_parser = _parser()
    args = parser.parse_args(raw_argv)

    if args.action == "request" and not _has_request_separator(raw_argv):
        request_parser.error("request requires '--' before COMMAND")

    try:
        if args.action == "request":
            command = args.command[1:] if args.command and args.command[0] == "--" else args.command
            return _request(args.exchange, command, args.sudo)
        if args.action == "list":
            return _list(args.exchange)
        if args.action == "result":
            return _result(args.exchange, args.id)
        raise ClientError("unknown command")
    except (OSError, ValueError) as error:
        print(f"zima-host: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
