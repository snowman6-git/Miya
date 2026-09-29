"""rcon.py <port> <cmd...> : 벤치 서버 명령 (stdlib)"""
import socket, struct, sys


def pk(s, i, t, b):
    d = struct.pack("<ii", i, t) + b.encode() + b"\0\0"; s.sendall(struct.pack("<i", len(d)) + d)
    n = struct.unpack("<i", s.recv(4))[0]; r = b""
    while len(r) < n: r += s.recv(n - len(r))
    return r[8:-2].decode(errors="replace")


def run(port, *cmds):
    s = socket.create_connection(("127.0.0.1", int(port))); pk(s, 1, 3, "bench")
    return [pk(s, 2, 2, c) for c in cmds]


if __name__ == "__main__":
    print("\n".join(run(sys.argv[1], " ".join(sys.argv[2:]))))
