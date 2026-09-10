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
    commands = {"serve", "login", "key", "use", "status", "bot"}
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

    bot = sub.add_parser("bot", help="manage persistent Hierarchy/Hermes bots")
    bot.add_argument("--store", default=None)
    bot_sub = bot.add_subparsers(dest="bot_action", required=True)
    bot_sub.add_parser("list", help="list bots")
    bot_create = bot_sub.add_parser("create", help="create and provision a persistent bot")
    bot_create.add_argument("name")
    bot_create.add_argument("--job", required=True)
    bot_create.add_argument("--description", required=True)
    bot_create.add_argument("--provider", choices=["chatgpt", "grok", "openai", "xai", "openrouter"], default="chatgpt")
    bot_create.add_argument("--model", default=None)
    bot_create.add_argument("--reports-to", default=None)
    bot_message = bot_sub.add_parser("message", help="send work to another persistent bot")
    bot_message.add_argument("--from", dest="sender", required=True)
    bot_message.add_argument("--to", required=True)
    bot_message.add_argument("--text", required=True)

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
    if cmd == "bot":
        runtime = Runtime(home)
        try:
            if args.bot_action == "list":
                print(json.dumps({"bots": runtime.roster()}, indent=2))
                return 0
            if args.bot_action == "create":
                created = runtime.create(
                    args.name, args.job, args.description, reports_to=args.reports_to,
                    provider=args.provider, model=args.model,
                )
                if runtime._hermes is not None:
                    runtime._hermes.ensure_bot(created, runtime.store.instructions(created.id))
                print(json.dumps({"id": created.id, "name": created.name, "provider": created.provider, "model": created.model}))
                return 0
            if args.bot_action == "message":
                sender = _resolve_bot(runtime, args.sender)
                target = _resolve_bot(runtime, args.to)
                reply = runtime.dm(sender_id=sender.id, to_id=target.id, text=args.text)
                print(json.dumps({"bot_id": reply.bot_id, "text": reply.text}))
                return 0
        finally:
            runtime.close()
    if cmd == "login":
        print(json.dumps(oauth.login(home, args.provider), indent=2))
        return 0
    parser.print_help()
    return 2


def _resolve_bot(runtime: Runtime, value: str):
    try:
        return runtime.store.get(value)
    except KeyError:
        bot = runtime.store.find_by_name(value)
        if bot is None:
            raise ValueError(f"unknown bot {value!r}") from None
        return bot


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
