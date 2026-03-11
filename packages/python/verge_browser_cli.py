from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from verge_browser import VergeAuthError, VergeClient, VergeConfigError, VergeConflictError, VergeNotFoundError, VergeServerError, VergeValidationError

EXIT_OK = 0
EXIT_SERVER = 1
EXIT_CONFIG = 2
EXIT_AUTH = 3
EXIT_NOT_FOUND = 4
EXIT_CONFLICT = 5
EXIT_VALIDATION = 6


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="verge-browser")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--token", default=None)
    parser.add_argument("--json", action="store_true", dest="json_output")

    subparsers = parser.add_subparsers(dest="command", required=True)
    sandbox = subparsers.add_parser("sandbox")
    sandbox_subparsers = sandbox.add_subparsers(dest="sandbox_command", required=True)

    sandbox_subparsers.add_parser("list")

    create = sandbox_subparsers.add_parser("create")
    create.add_argument("--alias", default=None)
    create.add_argument("--width", type=int, default=1280)
    create.add_argument("--height", type=int, default=1024)
    create.add_argument("--default-url", default=None)
    create.add_argument("--image", default=None)

    get_cmd = sandbox_subparsers.add_parser("get")
    get_cmd.add_argument("id_or_alias")

    update = sandbox_subparsers.add_parser("update")
    update.add_argument("id_or_alias")
    update.add_argument("--alias", required=True)

    for name in ("pause", "resume", "rm", "cdp", "vnc"):
        cmd = sandbox_subparsers.add_parser(name)
        cmd.add_argument("id_or_alias")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        client = VergeClient(base_url=args.base_url, token=args.token)
    except VergeConfigError as exc:
        return _emit_error(str(exc), EXIT_CONFIG, args.json_output)

    try:
        result = _dispatch(client, args)
        _emit_result(result, args.json_output)
        return EXIT_OK
    except VergeConfigError as exc:
        return _emit_error(str(exc), EXIT_CONFIG, args.json_output)
    except VergeAuthError as exc:
        return _emit_error(str(exc), EXIT_AUTH, args.json_output)
    except VergeNotFoundError as exc:
        return _emit_error(str(exc), EXIT_NOT_FOUND, args.json_output)
    except VergeConflictError as exc:
        return _emit_error(str(exc), EXIT_CONFLICT, args.json_output)
    except VergeValidationError as exc:
        return _emit_error(str(exc), EXIT_VALIDATION, args.json_output)
    except VergeServerError as exc:
        return _emit_error(str(exc), EXIT_SERVER, args.json_output)
    finally:
        client.close()


def _dispatch(client: VergeClient, args: argparse.Namespace) -> Any:
    if args.command != "sandbox":
        raise VergeConfigError(f"unsupported command: {args.command}")

    if args.sandbox_command == "list":
        return client.list_sandboxes()
    if args.sandbox_command == "create":
        return client.create_sandbox(
            alias=args.alias,
            width=args.width,
            height=args.height,
            default_url=args.default_url,
            image=args.image,
        )
    if args.sandbox_command == "get":
        return client.get_sandbox(args.id_or_alias)
    if args.sandbox_command == "update":
        return client.update_sandbox(args.id_or_alias, alias=args.alias)
    if args.sandbox_command == "pause":
        return client.pause_sandbox(args.id_or_alias)
    if args.sandbox_command == "resume":
        return client.resume_sandbox(args.id_or_alias)
    if args.sandbox_command == "rm":
        return client.delete_sandbox(args.id_or_alias)
    if args.sandbox_command == "cdp":
        return client.get_cdp_info(args.id_or_alias)
    if args.sandbox_command == "vnc":
        return client.get_vnc_url(args.id_or_alias)
    raise VergeConfigError(f"unsupported sandbox command: {args.sandbox_command}")


def _emit_result(result: Any, json_output: bool) -> None:
    if json_output or isinstance(result, (dict, list)):
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return
    print(result)


def _emit_error(message: str, code: int, json_output: bool) -> int:
    payload = {"ok": False, "error": message, "exit_code": code}
    if json_output:
        print(json.dumps(payload, ensure_ascii=True, indent=2), file=sys.stderr)
    else:
        print(message, file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
