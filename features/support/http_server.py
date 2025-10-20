import socket
import sys
import threading
from contextlib import contextmanager


def http_response() -> bytes:
    response = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK"
    return response


@contextmanager
def simple_http_server(port: int):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    sock.listen(1)

    def handle_requests():
        while True:
            try:
                client, addr = sock.accept()
                client.sendall(http_response())
                client.close()
            except OSError:
                break

    thread = threading.Thread(target=handle_requests, daemon=True)
    thread.start()

    try:
        yield
    finally:
        sock.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python http_server.py <port>")
        sys.exit(1)

    port = int(sys.argv[1])
    with simple_http_server(port):
        print(f"HTTP server listening on port {port}")
        try:
            while True:
                pass
        except KeyboardInterrupt:
            pass
