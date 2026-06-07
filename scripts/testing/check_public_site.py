#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urljoin


DEFAULT_BASE_URL = "https://foxsterdev.github.io/xuunity-mcp/"


@dataclass(frozen=True)
class ExpectedPage:
    path: str
    required_text: tuple[str, ...]


EXPECTED_PAGES = (
    ExpectedPage("", ("XUUnity MCP", "lightweight Unity MCP server")),
    ExpectedPage("install.html", ("Install XUUnity MCP", "setup-plan")),
    ExpectedPage("comparison.html", ("XUUnity MCP vs", "validation-heavy")),
    ExpectedPage("use-cases.html", ("Unity MCP use cases", "compile validation")),
    ExpectedPage("alternatives.html", ("Best Unity MCP solutions", "XUUnity MCP")),
    ExpectedPage("what-is-unity-mcp.html", ("What is Unity MCP", "XUUnity MCP")),
    ExpectedPage("xuunity-vs-coplaydev-unity-mcp.html", ("XUUnity MCP", "CoplayDev")),
    ExpectedPage("clients/", ("Client Guides", "Codex")),
    ExpectedPage("articles/", ("XUUnity MCP articles", "Introducing XUUnity MCP")),
    ExpectedPage("articles/introducing-xuunity-mcp.html", ("Introducing XUUnity MCP", "safe Unity Editor automation")),
    ExpectedPage("articles/xuunity-mcp-vs-unity-mcp.html", ("XUUnity MCP vs Unity MCP", "validation-first")),
    ExpectedPage(
        "articles/run-unity-compile-checks-and-tests-through-mcp.html",
        ("run Unity compile checks and tests through MCP", "compile validation"),
    ),
    ExpectedPage("robots.txt", ("Sitemap:",)),
    ExpectedPage("sitemap.xml", ("https://foxsterdev.github.io/xuunity-mcp/", "articles/")),
)


def fetch_text(url: str, timeout_seconds: float) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "xuunity-mcp-site-check/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status = int(response.getcode() or 0)
            body = response.read().decode("utf-8", errors="replace")
            return status, body
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        return int(error.code), body


def check_site(base_url: str, timeout_seconds: float) -> list[str]:
    errors: list[str] = []
    normalized_base = base_url if base_url.endswith("/") else base_url + "/"
    for page in EXPECTED_PAGES:
        url = urljoin(normalized_base, page.path)
        try:
            status, body = fetch_text(url, timeout_seconds)
        except Exception as exc:  # noqa: BLE001 - keep this utility dependency-free.
            errors.append(f"{url}: request failed: {exc}")
            continue
        if status != 200:
            errors.append(f"{url}: expected HTTP 200, got HTTP {status}")
            continue
        for required in page.required_text:
            if required not in body:
                errors.append(f"{url}: missing required text {required!r}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the public XUUnity MCP GitHub Pages discovery surface.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    args = parser.parse_args(argv)

    errors = check_site(args.base_url, args.timeout_seconds)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"public_site=ok base_url={args.base_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
