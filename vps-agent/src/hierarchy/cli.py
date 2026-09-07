"""CLI: serve, API keys, OAuth login."""
from __future__ import annotations

import argparse
import json
import sys

from hierarchy import auth, oauth
from hierarchy.serve import DEFAULT_PORT, Server, default_home
from hierarchy.runtime import Runtime


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    commands = {"serve", "login", "key", "use", "status"}
    if not argv or argv[0] not in commands:
        argv = ["serve", *argv]
    parser = argparse.ArgumentParser(prog="hierarchy")
    sub = parser.add_subparsers(dest="cmd")

    serve = sub.add_parser("serve", help="run the local roster UI")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.add_argument("--store", default=None)

    login = sub.add_parser("login", help="OAuth device login for grok or chatgpt")
    login.add_argument("provider", choices=["grok", "chatgpt"])
    login.add_argument("--store", default=None)

    key = sub.add_parser("key", help="save an API key")
    key.add_argument("provider", choices=["openai", "xai", "openrouter"])
    key.add_argument("api_key")
    key.add_argument("--model", default=None)
    key.add_argument("--store", default=None)

    use = sub.add_parser("use", help="select the active provider")
    use.add_argument("provider", choices=["stub", *auth.PROVIDERS])
    use.add_argument("--store", default=None)

    status = sub.add_parser("status", help="show configured providers")
    status.add_argument("--store", default=None)

    args = parser.parse_args(argv)
    home = str(args.store or default_home())
    cmd = args.cmd or "serve"

    if cmd == "serve":
        runtime = Runtime(home)
        host = getattr(args, "host", "127.0.0.1")
        port = getattr(args, "port", DEFAULT_PORT)
        server = Server(runtime, host=host, port=port)
        print(f"hierarchy {server.url}  store={home}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            server.shutdown()
        return 0

    if cmd == "key":
        print(json.dumps(auth.set_key(home, args.provider, args.api_key, model=args.model), indent=2))
        return 0
    if cmd == "use":
        print(json.dumps(auth.set_active(home, args.provider), indent=2))
        return 0
    if cmd == "status":
        print(json.dumps(auth.public_status(home=home), indent=2))
        return 0
    if cmd == "login":
        print(json.dumps(oauth.login(home, args.provider), indent=2))
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
