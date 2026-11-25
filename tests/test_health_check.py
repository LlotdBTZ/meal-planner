"""deploy/health-check.sh: a deploy counts as up only if /health reports its version.

Runs the real script against a throwaway HTTP server on localhost (no network).
"""

import socket
import subprocess
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "deploy" / "health-check.sh"


class _Server:
    """Answers GET /health with each queued (status, body) in turn, repeating the last."""

    def __init__(self) -> None:
        self.responses: list[tuple[int, str]] = [(200, "{}")]
        self.requests = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 (stdlib name)
                status, body = outer.responses[min(outer.requests, len(outer.responses) - 1)]
                outer.requests += 1
                data = body.encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args: object) -> None:  # keep test output quiet
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}/health"


@pytest.fixture
def server() -> Iterator[_Server]:
    s = _Server()
    thread = threading.Thread(target=s.httpd.serve_forever, daemon=True)
    thread.start()
    yield s
    s.httpd.shutdown()
    s.httpd.server_close()


def _check(url: str, tag: str, tries: int = 1) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), url, tag, str(tries)], capture_output=True, text=True, timeout=30
    )


def test_matching_version_is_up(server):
    server.responses = [(200, '{"status":"ok","version":"0.4.0"}')]
    assert _check(server.url, "v0.4.0").returncode == 0


def test_spaces_in_json_are_fine(server):
    server.responses = [(200, '{"status": "ok", "version": "1.2.3"}')]
    assert _check(server.url, "v1.2.3").returncode == 0


def test_wrong_version_fails_and_says_why(server):
    server.responses = [(200, '{"status":"ok","version":"0.3.1"}')]
    result = _check(server.url, "v0.4.0")
    assert result.returncode == 1
    assert "0.4.0" in result.stderr
    assert "0.3.1" in result.stderr


def test_waits_for_the_new_version(server):
    # Right after a restart the old process may still answer briefly.
    server.responses = [
        (200, '{"status":"ok","version":"0.3.1"}'),
        (200, '{"status":"ok","version":"0.4.0"}'),
    ]
    assert _check(server.url, "v0.4.0", tries=3).returncode == 0
    assert server.requests == 2


def test_releases_before_0_4_0_need_only_a_200(server):
    # They don't report a version, and update.sh still deploys them (rollbacks).
    server.responses = [(200, '{"status":"ok"}')]
    assert _check(server.url, "v0.3.1").returncode == 0


@pytest.mark.parametrize("tag", ["v0.4.0", "v0.10.0", "v1.0.0"])
def test_missing_version_fails_from_0_4_0(server, tag):
    server.responses = [(200, '{"status":"ok"}')]
    result = _check(server.url, tag)
    assert result.returncode == 1
    assert "no version" in result.stderr


def test_error_status_fails_even_with_right_version(server):
    server.responses = [(500, '{"status":"ok","version":"0.4.0"}')]
    result = _check(server.url, "v0.4.0")
    assert result.returncode == 1
    assert "no successful response" in result.stderr


def test_nothing_listening_fails():
    with socket.socket() as s:  # grab a free port, then close it
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    result = _check(f"http://127.0.0.1:{port}/health", "v0.4.0")
    assert result.returncode == 1
    assert "no successful response" in result.stderr


def test_rejects_a_bad_tag(server):
    result = _check(server.url, "latest")
    assert result.returncode == 2
