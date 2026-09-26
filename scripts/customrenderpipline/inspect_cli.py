"""Standalone observer client. stdout is one JSON response, including errors."""
import argparse
import json
from pathlib import Path
import sys

try:
    from .observer_transport import error_response, request, MAX_REQUEST_BYTES
except ImportError:
    from observer_transport import error_response, request, MAX_REQUEST_BYTES


class _HelpRequested(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)

    def print_help(self, file=None):
        super().print_help(file=sys.stderr if file is None else file)

    def exit(self, status=0, message=None):
        if status == 0:
            raise _HelpRequested(self.format_help())
        raise ValueError(message or "Invalid command line")


def _parser():
    parser = _Parser(description=__doc__)
    parser.add_argument("--session", required=True, help="Observer session directory")
    parser.add_argument("--timeout", type=float, default=10, help="Timeout in seconds (0 < value <= 300)")
    commands = parser.add_subparsers(dest="operation", required=True)
    for operation in ("list", "inspect", "compare", "read"):
        command = commands.add_parser(operation)
        command.add_argument("--graph", required=True)
        if operation in ("inspect", "compare"):
            command.add_argument("--region", type=int, nargs=4, required=True, metavar=("X", "Y", "W", "H"))
            command.add_argument("--fields", nargs="+")
        if operation == "inspect":
            command.add_argument("--export", action="store_true")
        if operation == "compare":
            command.add_argument("--reference", required=True, help="Reference NPZ path")
            command.add_argument("--rules", required=True, help="Rules JSON path")
            command.add_argument("--mask", help="Boolean coverage key in the reference NPZ")
        if operation == "read":
            command.add_argument("--output", required=True, help="Marked output PASS.PORT")
            command.add_argument("--mip", type=int, default=0)
            command.add_argument("--slice", type=int, default=0)
    return parser


def _arguments(options):
    arguments = {}
    if options.operation == "list":
        return arguments
    if options.operation == "read":
        return {"output": options.output, "mip": options.mip, "slice": options.slice}
    arguments["region"] = options.region
    if options.fields is not None:
        arguments["fields"] = options.fields
    if options.operation == "inspect":
        arguments["export"] = options.export
    else:
        arguments["reference"] = str(Path(options.reference).resolve())
        rules_path = Path(options.rules).resolve()
        with rules_path.open("rb") as stream:
            content = stream.read(MAX_REQUEST_BYTES + 1)
        if len(content) > MAX_REQUEST_BYTES:
            raise ValueError("Rules JSON exceeds the request size limit")
        arguments["rules"] = json.loads(content.decode("utf-8"))
        if not isinstance(arguments["rules"], dict):
            raise ValueError("Rules JSON must contain an object")
        if options.mask is not None:
            arguments["mask"] = options.mask
    return arguments


def main(argv=None):
    options = None
    try:
        options = _parser().parse_args(argv)
        response = request(options.session, options.operation, options.graph,
                           _arguments(options), timeout=options.timeout)
    except _HelpRequested as exc:
        response = error_response("", "")
        response.pop("error")
        response.update(status="ok", result={"help": str(exc)})
    except (ValueError, OSError, RecursionError) as exc:
        response = error_response("invalid_arguments", str(exc), graph=getattr(options, "graph", None))
    print(json.dumps(response, ensure_ascii=True, allow_nan=False))
    if response["status"] == "ok":
        return 0
    if response["status"] == "comparison_failed":
        return 1
    return 3 if response.get("error", {}).get("code") == "timeout" else 2


if __name__ == "__main__":
    sys.exit(main())
