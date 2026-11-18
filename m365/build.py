"""Builds the Microsoft 365 Copilot package of the Grunt plugin.

The package is a Microsoft 365 app ZIP: `manifest.json`, two icons, the skills
(`agentSkills`) and Grunt's MCP server as a connector (`agentConnectors`). The
skills come from `agent-plugins/grunt`, the generated plugin for harnesses other
than Claude and Codex, which already leaves out the Claude-only skills and gives
the rest their `grunt-` names. README.md in this folder says what else changes.

Run from the repository root:
    python m365/build.py
    python m365/build.py --mcp-url https://grunt.example.com/mcp
    python m365/build.py --oauth-reference-id <id from the Teams Developer Portal>

Standard library only.
"""

import argparse
import json
import re
import struct
import sys
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "grunt"
SKILLS_SOURCE = ROOT / "agent-plugins" / "grunt" / "skills"
M365 = ROOT / "m365"

MANIFEST_VERSION = "1.29"
SCHEMA = f"https://developer.microsoft.com/json-schemas/teams/v{MANIFEST_VERSION}/MicrosoftTeams.schema.json"
CLOUD_MCP_URL = "https://mcp.grunt.io/mcp"

TOOL_DESCRIPTION_SOURCE = M365 / "toolDescription.json"
TOOL_DESCRIPTION_IN_PACKAGE = "tools/grunt-tools.json"
# The domains the chart widget declares it needs. Cowork blocks every declared
# domain that `validDomains` does not list, and shows a warning naming the plugin.
WIDGET_DOMAINS_SOURCE = M365 / "widgetDomains.json"

# Limits Microsoft documents for a plugin package (Build plugins for Copilot Cowork).
MAX_SKILLS = 20
MAX_COMPANION_FILES = 20
MAX_COMPANION_BYTES = 5 * 1024 * 1024
MAX_SKILL_BYTES = 10 * 1024 * 1024
MAX_DESCRIPTION = 1024
# Work IQ Dev Tools' packaging limit for a JSON file; the tool list is the large one.
MAX_JSON_BYTES = 1024 * 1024
SKILL_NAME = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
SAFE_FILE_NAME = re.compile(r"[A-Za-z0-9_.!\- ]+")
RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


class BuildError(Exception):
    pass


def app_id(mcp_url):
    """One fixed app id per Grunt address, so a test package for another Grunt
    installs beside the cloud one instead of replacing it."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"grunt-m365-plugin:{mcp_url}"))


def default_skills():
    """Every skill of the generated plugin, in name order."""
    return tuple(sorted(p.name for p in SKILLS_SOURCE.iterdir() if (p / "SKILL.md").is_file()))


def skill_files(skill):
    """The files of one packaged skill, as {path inside the skill folder: bytes}."""
    source = SKILLS_SOURCE / skill
    if not (source / "SKILL.md").is_file():
        raise BuildError(f"no skill '{skill}' in {SKILLS_SOURCE}")
    files = {}
    for path in sorted(p for p in source.rglob("*") if p.is_file()):
        relative = path.relative_to(source).as_posix()
        if relative == "CONNECT.md":
            # The plugin's CONNECT.md lists the steps for the other apps.
            files[relative] = (M365 / "CONNECT.md").read_text(encoding="utf-8").encode("utf-8")
        else:
            files[relative] = path.read_bytes()
    return files


def check_skill(name, files):
    """The package rules Microsoft's upload validates (ASKILL-P001 to P008 and the
    companion-file rules), so a build fails here instead of at upload."""
    if not SKILL_NAME.fullmatch(name) or len(name) > 64:
        raise BuildError(f"skill name '{name}' is not kebab-case of at most 64 characters")
    text = files["SKILL.md"].decode("utf-8")
    front = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    if not front:
        raise BuildError(f"{name}/SKILL.md has no front matter")
    declared = re.search(r"^name: (\S+)$", front.group(1), re.MULTILINE)
    description = re.search(r"^description: (.+)$", front.group(1), re.MULTILINE)
    if not declared or declared.group(1) != name:
        raise BuildError(f"{name}/SKILL.md must declare 'name: {name}'")
    if not description or not 1 <= len(description.group(1)) <= MAX_DESCRIPTION:
        raise BuildError(f"{name}/SKILL.md needs a description of 1 to {MAX_DESCRIPTION} characters")
    companions = {path: data for path, data in files.items() if path != "SKILL.md"}
    if len(companions) > MAX_COMPANION_FILES:
        raise BuildError(f"{name} has {len(companions)} companion files; the limit is {MAX_COMPANION_FILES}")
    if sum(len(data) for data in companions.values()) > MAX_SKILL_BYTES:
        raise BuildError(f"{name}'s companion files exceed {MAX_SKILL_BYTES} bytes in total")
    for path, data in companions.items():
        if len(data) > MAX_COMPANION_BYTES:
            raise BuildError(f"{name}/{path} is larger than {MAX_COMPANION_BYTES} bytes")
        for part in path.split("/"):
            if not SAFE_FILE_NAME.fullmatch(part) or part.split(".")[0].upper() in RESERVED_NAMES:
                raise BuildError(f"{name}/{path}: '{part}' is not a file name Microsoft 365 accepts")


def png_size(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise BuildError("icon is not a PNG file")
    return struct.unpack(">II", data[16:24])


def load_tools(path):
    """The tool list a connector declares: the server's `tools/list` result, kept to
    the three fields Microsoft documents for this file."""
    tools = json.loads(path.read_text(encoding="utf-8"))["tools"]
    if not tools:
        raise BuildError(f"{path} lists no tools")
    return {"tools": [{"name": t["name"], "description": t.get("description", ""), "inputSchema": t["inputSchema"]} for t in tools]}


def connector(mcp_url, oauth_reference_id, auth_type, has_tools):
    if not mcp_url.startswith("https://"):
        raise BuildError("the MCP address must be an https:// URL")
    server = {"mcpServerUrl": mcp_url}
    if has_tools:
        server["mcpToolDescription"] = {"file": TOOL_DESCRIPTION_IN_PACKAGE}
    if oauth_reference_id:
        server["authorization"] = {"type": auth_type, "referenceId": oauth_reference_id}
    # With no authorization, Cowork registers itself as an OAuth client with
    # Grunt's sign-in server (RFC 7591). Copilot Chat needs a reference id.
    return {
        "id": "grunt",
        "displayName": "Grunt",
        "description": (
            "Create and change Grunt charts and tables (bar, line, area, combined, waterfall, Mekko, "
            "scatter, pie, radar, dumbbell, Gantt and formatted tables), and read and change the "
            "presentations open in the user's PowerPoint when the Grunt add-in is running and signed in."
        ),
        "toolSource": {"remoteMcpServer": server},
    }


def widget_domains():
    if not WIDGET_DOMAINS_SOURCE.is_file():
        return []
    return json.loads(WIDGET_DOMAINS_SOURCE.read_text(encoding="utf-8"))["validDomains"]


def manifest(version, skills, mcp_url, oauth_reference_id, auth_type, has_tools):
    cloud = mcp_url == CLOUD_MCP_URL
    short_name = "Grunt" if cloud else "Grunt (test)"
    domains = widget_domains()
    return {
        "$schema": SCHEMA,
        "manifestVersion": MANIFEST_VERSION,
        "version": version,
        "id": app_id(mcp_url),
        "developer": {
            "name": "Grunt",
            "websiteUrl": "https://www.grunt.pro",
            "privacyUrl": "https://www.grunt.pro/legal/privacy-policy",
            "termsOfUseUrl": "https://www.grunt.pro/legal/terms",
        },
        "name": {"short": short_name, "full": f"{short_name} charts and tables"},
        "description": {
            "short": "Editable charts and tables for PowerPoint decks and reports.",
            "full": (
                "Grunt makes charts and tables that stay editable: bar, line, area, combined, waterfall, "
                "Mekko, scatter, pie, radar, dumbbell and Gantt charts, and formatted tables. Ask for a "
                "chart in plain language and change it with follow-up requests. With PowerPoint open and "
                "the Grunt add-in signed in, charts and tables are placed on your slides as Grunt objects "
                "that you can keep editing in PowerPoint. Sign in with your own Grunt account."
            ),
        },
        "icons": {"color": "color.png", "outline": "outline.png"},
        "accentColor": "#00D6A8",
        "agentSkills": [{"folder": f"./skills/{skill}"} for skill in skills],
        "agentConnectors": [connector(mcp_url, oauth_reference_id, auth_type, has_tools)],
        **({"validDomains": domains} if domains else {}),
    }


def check_manifest(m):
    limits = [
        (m["name"]["short"], 30), (m["name"]["full"], 100), (m["description"]["short"], 80),
        (m["description"]["full"], 4000), (m["developer"]["name"], 32),
    ]
    for text, limit in limits:
        if len(text) > limit:
            raise BuildError(f"'{text[:40]}...' is longer than {limit} characters")
    if len(m["agentSkills"]) > MAX_SKILLS:
        raise BuildError(f"a package holds at most {MAX_SKILLS} skills")
    if len(m.get("validDomains", [])) > 100:
        raise BuildError("a manifest lists at most 100 valid domains")
    if not re.fullmatch(r"\d+\.\d+\.\d+", m["version"]):
        raise BuildError(f"version '{m['version']}' is not major.minor.patch")


def build_package(out_dir, mcp_url=CLOUD_MCP_URL, skills=None, oauth_reference_id=None,
                  auth_type="OAuthPluginVault", tool_description=TOOL_DESCRIPTION_SOURCE):
    """Writes the ZIP and returns its path."""
    version = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    skills = tuple(skills) if skills else default_skills()
    has_tools = tool_description is not None and Path(tool_description).is_file()
    entries = {}
    for skill in skills:
        files = skill_files(skill)
        check_skill(skill, files)
        for path, data in files.items():
            entries[f"skills/{skill}/{path}"] = data
    for icon, size in (("color.png", (192, 192)), ("outline.png", (32, 32))):
        data = (M365 / icon).read_bytes()
        if png_size(data) != size:
            raise BuildError(f"m365/{icon} must be {size[0]}x{size[1]} pixels")
        entries[icon] = data
    if has_tools:
        tools = json.dumps(load_tools(Path(tool_description)), separators=(",", ":")).encode("utf-8")
        if len(tools) > MAX_JSON_BYTES:
            raise BuildError(f"the tool list is {len(tools)} bytes; a JSON file in the package may be {MAX_JSON_BYTES}")
        entries[TOOL_DESCRIPTION_IN_PACKAGE] = tools
    m = manifest(version, skills, mcp_url, oauth_reference_id, auth_type, has_tools)
    check_manifest(m)
    entries["manifest.json"] = json.dumps(m, indent=2).encode("utf-8")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = "" if mcp_url == CLOUD_MCP_URL else "-test"
    path = out_dir / f"grunt-m365{target}-{version}.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(entries):
            # A fixed timestamp keeps the ZIP identical for identical input.
            archive.writestr(zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)), entries[name], zipfile.ZIP_DEFLATED)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--mcp-url", default=CLOUD_MCP_URL, help="address of the Grunt MCP server (default: Grunt's cloud service)")
    parser.add_argument("--skills", help="comma-separated skills to include, for example grunt-powerpoint (default: all)")
    parser.add_argument("--oauth-reference-id", help="OAuth registration id from the Teams Developer Portal; without it Cowork registers itself")
    parser.add_argument("--auth-type", default="OAuthPluginVault", choices=["OAuthPluginVault", "DynamicClientRegistration"],
                        help="what the reference id refers to (default: OAuthPluginVault)")
    parser.add_argument("--no-tool-description", action="store_true", help="leave the packaged tool list out")
    parser.add_argument("--out", default=str(M365 / "dist"), help="output folder (default: m365/dist)")
    args = parser.parse_args()
    try:
        path = build_package(
            args.out, args.mcp_url, [s for s in (args.skills or "").split(",") if s], args.oauth_reference_id,
            args.auth_type, None if args.no_tool_description else TOOL_DESCRIPTION_SOURCE,
        )
    except BuildError as error:
        sys.exit(f"error: {error}")
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
    print(f"{path} ({path.stat().st_size // 1024} KB, {len(names)} files)")
    if TOOL_DESCRIPTION_IN_PACKAGE not in names:
        print("note: no tool list in the package; Cowork needs one (see m365/README.md).")


if __name__ == "__main__":
    main()
