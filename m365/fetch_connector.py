"""Reads from a Grunt MCP server what the Microsoft 365 package states about it.

Writes two files into this folder, which m365/build.py puts into the package:

- toolDescription.json: the server's tools, from `tools/list`. Copilot Cowork
  requires a packaged tool list.
- widgetDomains.json: the domains the chart widget declares it needs, from the
  widget resource's `_meta.ui.csp`. Cowork blocks every declared domain that the
  package's `validDomains` does not list.

Run it when the server's tools or widget change, then rebuild:

    python m365/fetch_connector.py --url http://localhost:5044/mcp
    GRUNT_MCP_TOKEN=... python m365/fetch_connector.py --url https://mcp.grunt.io/mcp

The token is read from the GRUNT_MCP_TOKEN environment variable, never from the
command line. A local development server needs none.

Standard library only.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

FOLDER = Path(__file__).resolve().parent
PROTOCOL_VERSION = "2025-06-18"
# The fields of a tool that the file keeps. Copilot reads name, description and
# inputSchema; title and annotations are kept for people reviewing the list.
KEPT = ("name", "title", "description", "inputSchema", "annotations")
CSP_KEYS = ("connectDomains", "resourceDomains", "frameDomains")


class McpSession:
    def __init__(self, url, token):
        self.url = url
        self.headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
        self.next_id = 0

    def post(self, message):
        request = urllib.request.Request(self.url, json.dumps(message).encode("utf-8"), self.headers, method="POST")
        with urllib.request.urlopen(request, timeout=60) as response:
            session = response.headers.get("Mcp-Session-Id")
            if session:
                self.headers["Mcp-Session-Id"] = session
            body = response.read().decode("utf-8")
            if "text/event-stream" not in response.headers.get("Content-Type", ""):
                return json.loads(body) if body.strip() else None
        # Streamable HTTP may answer as server-sent events: take the event that
        # carries this request's response.
        for line in body.splitlines():
            if line.startswith("data:"):
                event = json.loads(line[5:])
                if event.get("id") == message.get("id"):
                    return event
        return None

    def request(self, method, params=None):
        self.next_id += 1
        message = {"jsonrpc": "2.0", "id": self.next_id, "method": method}
        if params is not None:
            message["params"] = params
        answer = self.post(message)
        if answer is None or "error" in answer:
            raise RuntimeError(f"{method} failed: {answer and answer['error']}")
        return answer["result"]

    def notify(self, method):
        self.post({"jsonrpc": "2.0", "method": method})

    def list_all(self, method, key):
        items, cursor = [], None
        while True:
            page = self.request(method, {"cursor": cursor} if cursor else {})
            items.extend(page.get(key, []))
            cursor = page.get("nextCursor")
            if not cursor:
                return items


def connect(url, token):
    session = McpSession(url, token)
    initialized = session.request("initialize", {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "grunt-m365-package-build", "version": "1"},
    })
    session.headers["MCP-Protocol-Version"] = initialized.get("protocolVersion", PROTOCOL_VERSION)
    session.notify("notifications/initialized")
    return session


def model_visible(tool):
    """Tools a widget alone may call are not offered to the model, so they do not
    belong in the list an agent reads."""
    meta = tool.get("_meta") or {}
    visibility = (meta.get("ui") or {}).get("visibility")
    return (visibility is None or "model" in visibility) and meta.get("openai/visibility") != "private"


def host_of(origin):
    """`https://*.example.com` as a manifest `validDomains` entry: `*.example.com`."""
    return origin.split("://", 1)[-1].split("/", 1)[0]


def widget_domains(session, tools):
    """Every domain the widgets of these tools declare, as host names."""
    uris = {((tool.get("_meta") or {}).get("ui") or {}).get("resourceUri") for tool in tools} - {None}
    hosts = set()
    for uri in sorted(uris):
        for content in session.request("resources/read", {"uri": uri}).get("contents", []):
            ui = (content.get("_meta") or {}).get("ui") or {}
            csp = ui.get("csp") or {}
            origins = [origin for key in CSP_KEYS for origin in csp.get(key, [])]
            if ui.get("domain"):
                origins.append(ui["domain"])
            hosts.update(host_of(origin) for origin in origins)
    return sorted(hosts)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--url", required=True, help="the MCP endpoint, for example https://mcp.grunt.io/mcp")
    parser.add_argument("--out", default=str(FOLDER), help="folder to write into (default: m365)")
    args = parser.parse_args()
    try:
        session = connect(args.url, os.environ.get("GRUNT_MCP_TOKEN"))
        tools = session.list_all("tools/list", "tools")
        domains = widget_domains(session, tools)
    except urllib.error.HTTPError as error:
        hint = " Set GRUNT_MCP_TOKEN to an access token for this server." if error.code == 401 else ""
        sys.exit(f"error: {args.url} answered {error.code} {error.reason}.{hint}")
    except (urllib.error.URLError, RuntimeError) as error:
        sys.exit(f"error: {error}")
    out = Path(args.out)
    listed = sorted((t for t in tools if model_visible(t)), key=lambda t: t["name"])
    # One tool per line: the chart schemas are large, and this keeps a changed
    # tool to one changed line in a diff.
    lines = [json.dumps({key: tool[key] for key in KEPT if key in tool}, ensure_ascii=False) for tool in listed]
    # Written as bytes so the files have the same line endings on every platform.
    (out / "toolDescription.json").write_bytes(('{"tools": [\n' + ",\n".join(lines) + "\n]}\n").encode("utf-8"))
    (out / "widgetDomains.json").write_bytes((json.dumps({"validDomains": domains}, indent=2) + "\n").encode("utf-8"))
    print(f"{out / 'toolDescription.json'}: {len(listed)} tools ({len(tools) - len(listed)} widget-only tools left out)")
    print(f"{out / 'widgetDomains.json'}: {len(domains)} domains")


if __name__ == "__main__":
    main()
