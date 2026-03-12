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
    parser.add_argument("--json", action="store_true", dest="json_output", default=argparse.SUPPRESS)

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Shared parent parser for common options on subcommands
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("--json", action="store_true", dest="json_output", default=argparse.SUPPRESS)
    sandbox = subparsers.add_parser("sandbox", parents=[parent_parser])
    sandbox_subparsers = sandbox.add_subparsers(dest="sandbox_command", required=True)

    sandbox_subparsers.add_parser("list", parents=[parent_parser])

    create = sandbox_subparsers.add_parser("create", parents=[parent_parser])
    create.add_argument("--alias", default=None)
    create.add_argument("--kind", default="xvfb_vnc", choices=["xvfb_vnc", "xpra"])
    create.add_argument("--width", type=int, default=1280)
    create.add_argument("--height", type=int, default=1024)
    create.add_argument("--default-url", default=None)
    create.add_argument("--image", default=None)

    get_cmd = sandbox_subparsers.add_parser("get", parents=[parent_parser])
    get_cmd.add_argument("id_or_alias")

    update = sandbox_subparsers.add_parser("update", parents=[parent_parser])
    update.add_argument("id_or_alias")
    update.add_argument("--alias", required=True)

    for name in ("pause", "resume", "rm", "restart", "cdp", "session"):
        cmd = sandbox_subparsers.add_parser(name, parents=[parent_parser])
        cmd.add_argument("id_or_alias")

    # Browser subcommand
    browser = subparsers.add_parser("browser", parents=[parent_parser])
    browser_subparsers = browser.add_subparsers(dest="browser_command", required=True)

    screenshot = browser_subparsers.add_parser("screenshot", parents=[parent_parser])
    screenshot.add_argument("id_or_alias")
    screenshot.add_argument("--type", default="page", choices=["window", "page"])
    screenshot.add_argument("--format", default="jpeg", choices=["png", "jpeg", "webp"])
    screenshot.add_argument("--target-id", default=None)
    screenshot.add_argument("--output", default=None, help="Write screenshot to file")

    actions = browser_subparsers.add_parser("actions", parents=[parent_parser])
    actions.add_argument("id_or_alias")
    actions.add_argument("--input", required=True, help="JSON file with actions payload")

    # Files subcommand
    files = subparsers.add_parser("files", parents=[parent_parser])
    files_subparsers = files.add_subparsers(dest="files_command", required=True)

    list_cmd = files_subparsers.add_parser("list", parents=[parent_parser])
    list_cmd.add_argument("id_or_alias")
    list_cmd.add_argument("path", nargs="?", default="/workspace")

    read = files_subparsers.add_parser("read", parents=[parent_parser])
    read.add_argument("id_or_alias")
    read.add_argument("path")

    write = files_subparsers.add_parser("write", parents=[parent_parser])
    write.add_argument("id_or_alias")
    write.add_argument("path")
    write.add_argument("--content", required=True)
    write.add_argument("--overwrite", action="store_true")

    upload = files_subparsers.add_parser("upload", parents=[parent_parser])
    upload.add_argument("id_or_alias")
    upload.add_argument("local_path")

    download = files_subparsers.add_parser("download", parents=[parent_parser])
    download.add_argument("id_or_alias")
    download.add_argument("path")
    download.add_argument("--output", default=None)

    rm = files_subparsers.add_parser("rm", parents=[parent_parser])
    rm.add_argument("id_or_alias")
    rm.add_argument("path")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    json_output = bool(getattr(args, "json_output", False))

    try:
        client = VergeClient(base_url=args.base_url, token=args.token)
    except VergeConfigError as exc:
        return _emit_error(str(exc), EXIT_CONFIG, json_output)

    try:
        result = _dispatch(client, args)
        _emit_result(result, json_output)
        return EXIT_OK
    except VergeConfigError as exc:
        return _emit_error(str(exc), EXIT_CONFIG, json_output)
    except VergeAuthError as exc:
        return _emit_error(str(exc), EXIT_AUTH, json_output)
    except VergeNotFoundError as exc:
        return _emit_error(str(exc), EXIT_NOT_FOUND, json_output)
    except VergeConflictError as exc:
        return _emit_error(str(exc), EXIT_CONFLICT, json_output)
    except VergeValidationError as exc:
        return _emit_error(str(exc), EXIT_VALIDATION, json_output)
    except VergeServerError as exc:
        return _emit_error(str(exc), EXIT_SERVER, json_output)
    finally:
        client.close()


def _dispatch(client: VergeClient, args: argparse.Namespace) -> Any:
    if args.command == "browser":
        if args.browser_command == "screenshot":
            result = client.get_browser_screenshot(
                args.id_or_alias,
                type=args.type,
                format=args.format,
                target_id=args.target_id,
            )
            if args.output:
                import base64
                data = base64.b64decode(result["data_base64"])
                with open(args.output, "wb") as f:
                    f.write(data)
                return {"output": args.output, **result}
            return result
        if args.browser_command == "actions":
            import json
            try:
                with open(args.input, "r") as f:
                    payload = json.load(f)
            except json.JSONDecodeError as exc:
                raise VergeConfigError(f"invalid JSON in actions file: {exc}")
            if not isinstance(payload, dict):
                raise VergeConfigError("actions payload must be a JSON object")
            return client.execute_browser_actions(
                args.id_or_alias,
                payload.get("actions", []),
                continue_on_error=payload.get("continue_on_error", False),
                screenshot_after=payload.get("screenshot_after", False),
            )
        raise VergeConfigError(f"unsupported browser command: {args.browser_command}")

    if args.command == "files":
        if args.files_command == "list":
            return client.list_files(args.id_or_alias, args.path)
        if args.files_command == "read":
            result = client.read_file(args.id_or_alias, args.path)
            return result if bool(getattr(args, "json_output", False)) else result.get("content", "")
        if args.files_command == "write":
            return client.write_file(args.id_or_alias, args.path, args.content, overwrite=args.overwrite)
        if args.files_command == "upload":
            with open(args.local_path, "rb") as f:
                data = f.read()
            return client.upload_file(args.id_or_alias, args.local_path, data)
        if args.files_command == "download":
            result = client.download_file(args.id_or_alias, args.path)
            if args.output:
                with open(args.output, "wb") as f:
                    f.write(result["data"])
                return {"path": args.path, "output": args.output}
            import base64
            return {"path": args.path, "data_base64": base64.b64encode(result["data"]).decode()}
        if args.files_command == "rm":
            return client.delete_file(args.id_or_alias, args.path)
        raise VergeConfigError(f"unsupported files command: {args.files_command}")

    if args.command != "sandbox":
        raise VergeConfigError(f"unsupported command: {args.command}")

    if args.sandbox_command == "list":
        return client.list_sandboxes()
    if args.sandbox_command == "create":
        return client.create_sandbox(
            alias=args.alias,
            kind=args.kind,
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
    if args.sandbox_command == "restart":
        return client.restart_browser(args.id_or_alias)
    if args.sandbox_command == "cdp":
        return client.get_cdp_info(args.id_or_alias)
    if args.sandbox_command == "session":
        return client.get_session_url(args.id_or_alias)
    raise VergeConfigError(f"unsupported sandbox command: {args.sandbox_command}")


def _emit_result(result: Any, json_output: bool) -> None:
    if json_output:
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return
    print(_format_plain_text(result))


def _format_plain_text(value: Any, indent: int = 0) -> str:
    prefix = "  " * indent

    if value is None:
        return "null"
    if isinstance(value, str):
        return _format_string_value(value, indent)
    if isinstance(value, (bool, int, float)):
        return str(value)
    if isinstance(value, list):
        if not value:
            return f"{prefix}(empty)"
        rendered: list[str] = []
        for item in value:
            if _is_primitive(item):
                rendered.append(f"{prefix}- {_format_scalar(item)}")
                continue
            nested = _format_plain_text(item, indent + 1).splitlines()
            first = nested[0] if nested else ""
            rendered.append(f"{prefix}- {first}")
            rendered.extend(f"{prefix}  {line}" for line in nested[1:])
        return "\n".join(rendered)
    if isinstance(value, dict):
        if not value:
            return f"{prefix}(empty)"
        return "\n".join(_format_object_entry(key, child, indent) for key, child in value.items())
    return str(value)


def _format_object_entry(key: str, value: Any, indent: int) -> str:
    prefix = "  " * indent
    if _is_primitive(value):
        return f"{prefix}{key}: {_format_scalar(value)}"
    rendered = _format_plain_text(value, indent + 1)
    return f"{prefix}{key}:\n{rendered}"


def _format_string_value(value: str, indent: int) -> str:
    if "\n" not in value:
        return value
    prefix = "  " * indent
    rendered = "\n".join(f"{prefix}  {line}" for line in value.splitlines())
    return f"|\n{rendered}"


def _format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True) if "\n" in value else value
    return str(value)


def _is_primitive(value: Any) -> bool:
    return value is None or isinstance(value, (str, bool, int, float))


def _emit_error(message: str, code: int, json_output: bool) -> int:
    payload = {"ok": False, "error": message, "exit_code": code}
    if json_output:
        print(json.dumps(payload, ensure_ascii=True, indent=2), file=sys.stderr)
    else:
        print(message, file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
