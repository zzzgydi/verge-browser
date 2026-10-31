"""One command, one connection. Never launch or retry a browser operation."""

import json
import socket
import sys


def main():
    command = json.load(sys.stdin)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(30)
        client.connect("/run/sandbox/camoufox.sock")
        client.sendall((json.dumps(command) + "\n").encode())
        response = json.loads(client.makefile("rb").readline(24 * 1024 * 1024))
    print(json.dumps(response))
    return 0 if response["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
