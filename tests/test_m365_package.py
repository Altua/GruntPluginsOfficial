"""Checks the Microsoft 365 Copilot package that m365/build.py makes.

Run from the repository root:
    python -m unittest discover -s tests -p "test_*.py"
"""

import importlib.util
import json
import re
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
M365 = ROOT / "m365"

_spec = importlib.util.spec_from_file_location("m365_build", M365 / "build.py")
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)

# Customers' tenants keep the plugin installed under this id, so it must not
# change once the package has been published.
CLOUD_APP_ID = "1afa0948-dd57-5f43-8eb9-26861f18f05a"
TEST_MCP_URL = "https://grunt.example.com/mcp"
SKILLS = ["grunt-html", "grunt-powerpoint", "grunt-pptx"]


def package(**options):
    """Builds into a temporary folder and returns {path in the ZIP: bytes}."""
    with tempfile.TemporaryDirectory() as folder:
        path = build.build_package(folder, **options)
        with zipfile.ZipFile(path) as archive:
            return {name: archive.read(name) for name in archive.namelist()}


def manifest_of(files):
    return json.loads(files["manifest.json"])


def server_of(files):
    return manifest_of(files)["agentConnectors"][0]["toolSource"]["remoteMcpServer"]


class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = package()
        cls.manifest = manifest_of(cls.files)

    def test_package_holds_the_manifest_icons_skills_and_tool_list(self):
        for name in ("manifest.json", "color.png", "outline.png", "tools/grunt-tools.json"):
            self.assertIn(name, self.files)
        for name in self.files:
            self.assertRegex(name, r"^(manifest\.json|color\.png|outline\.png|tools/|skills/)", name)
            self.assertNotIn("\\", name)

    def test_manifest_identifies_the_cloud_plugin(self):
        plugin = json.loads((ROOT / "plugins" / "grunt" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(self.manifest["manifestVersion"], "1.29")
        self.assertEqual(self.manifest["id"], CLOUD_APP_ID)
        self.assertEqual(self.manifest["version"], plugin["version"])
        self.assertEqual(self.manifest["name"]["short"], "Grunt")
        for key in ("websiteUrl", "privacyUrl", "termsOfUseUrl"):
            self.assertTrue(self.manifest["developer"][key].startswith("https://"), key)

    def test_manifest_texts_fit_their_limits(self):
        self.assertLessEqual(len(self.manifest["name"]["short"]), 30)
        self.assertLessEqual(len(self.manifest["description"]["short"]), 80)
        self.assertLessEqual(len(self.manifest["description"]["full"]), 4000)
        self.assertLessEqual(len(self.manifest["agentConnectors"][0]["description"]), 4000)

    def test_icons_have_the_sizes_microsoft_365_requires(self):
        for name, size in (("color.png", (192, 192)), ("outline.png", (32, 32))):
            self.assertEqual(struct.unpack(">II", self.files[name][16:24]), size, name)

    def test_every_declared_skill_is_in_the_package_under_its_own_name(self):
        folders = [entry["folder"] for entry in self.manifest["agentSkills"]]
        self.assertEqual(folders, [f"./skills/{name}" for name in SKILLS])
        for name in SKILLS:
            text = self.files[f"skills/{name}/SKILL.md"].decode("utf-8")
            self.assertEqual(re.search(r"^name: (\S+)$", text, re.MULTILINE).group(1), name)

    def test_skills_come_from_the_generated_plugin(self):
        # agent-plugins/grunt already leaves out the Claude-only skills and holds
        # the rest under their `grunt-` names.
        generated = ROOT / "agent-plugins" / "grunt" / "skills"
        self.assertEqual(SKILLS, sorted(p.name for p in generated.iterdir() if p.is_dir()))
        self.assertFalse([name for name in self.files if "slides" in name])

    def test_skills_keep_within_the_companion_file_limits(self):
        for name in SKILLS:
            companions = [f for f in self.files if f.startswith(f"skills/{name}/") and not f.endswith("/SKILL.md")]
            self.assertLessEqual(len(companions), 20, name)
            self.assertLessEqual(sum(len(self.files[f]) for f in companions), 10 * 1024 * 1024, name)

    def test_files_microsoft_365_does_not_use_are_left_out(self):
        for name in self.files:
            parts = name.split("/")
            self.assertFalse(any(part.startswith(".") for part in parts), name)
            self.assertNotIn("agents", parts, name)
            self.assertNotIn("assets", parts, name)
            self.assertFalse(parts[-1].startswith("test_"), name)

    def test_skills_name_each_other_by_their_packaged_names(self):
        for name in self.files:
            if name.endswith(".md"):
                text = self.files[name].decode("utf-8")
                self.assertIsNone(re.search(r"(?<![\w/.-])`?(powerpoint|pptx|html)`? skill\b", text), name)

    def test_connect_md_gives_the_microsoft_365_steps(self):
        expected = (M365 / "CONNECT.md").read_text(encoding="utf-8")
        packaged = [name for name in self.files if name.endswith("/CONNECT.md")]
        self.assertEqual(len(packaged), 2)
        for name in packaged:
            self.assertEqual(self.files[name].decode("utf-8"), expected, name)

    def test_links_between_skill_files_resolve_inside_the_package(self):
        for name in self.files:
            if not name.endswith(".md"):
                continue
            folder = name.rsplit("/", 1)[0]
            for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", self.files[name].decode("utf-8")):
                if not re.match(r"[a-z]+:", target):
                    self.assertIn(f"{folder}/{target}", self.files, f"{name} links to {target}")

    def test_tool_list_has_the_documented_shape(self):
        tools = json.loads(self.files["tools/grunt-tools.json"])["tools"]
        names = [tool["name"] for tool in tools]
        self.assertEqual(len(names), len(set(names)))
        for tool in tools:
            self.assertEqual(sorted(tool), ["description", "inputSchema", "name"], tool["name"])
            self.assertTrue(tool["description"], tool["name"])
        self.assertLess(len(self.files["tools/grunt-tools.json"]), 1024 * 1024)

    def test_tools_the_skills_name_are_in_the_tool_list(self):
        # A skill that tells Copilot to call a tool the connector does not list
        # fails in the middle of a request.
        tools = {tool["name"] for tool in json.loads(self.files["tools/grunt-tools.json"])["tools"]}
        named = set()
        for name in self.files:
            if name.endswith(".md"):
                named.update(re.findall(r"`((?:deck|create_or_update)_[a-z_]*[a-z])`", self.files[name].decode("utf-8")))
        self.assertTrue(named)
        self.assertEqual(sorted(named - tools), [])

    def test_widget_domains_are_listed_as_valid_domains(self):
        # Cowork blocks every domain the chart widget declares that is missing here.
        stored = json.loads((M365 / "widgetDomains.json").read_text(encoding="utf-8"))["validDomains"]
        self.assertEqual(self.manifest["validDomains"], stored)
        self.assertIn("mcp.grunt.io", stored)
        for domain in stored:
            self.assertRegex(domain, r"^(\*\.)?[a-z0-9-]+(\.[a-z0-9-]+)+$")

    def test_stored_tool_list_is_sorted_one_tool_per_line(self):
        text = (M365 / "toolDescription.json").read_text(encoding="utf-8")
        names = [tool["name"] for tool in json.loads(text)["tools"]]
        self.assertEqual(names, sorted(names))
        self.assertEqual(len(text.splitlines()), len(names) + 2)

    def test_same_input_gives_the_same_zip(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            self.assertEqual(build.build_package(first).read_bytes(), build.build_package(second).read_bytes())


class ConnectorTests(unittest.TestCase):
    def test_without_a_reference_the_host_registers_itself(self):
        server = server_of(package())
        self.assertEqual(server["mcpServerUrl"], "https://mcp.grunt.io/mcp")
        self.assertEqual(server["mcpToolDescription"], {"file": "tools/grunt-tools.json"})
        self.assertNotIn("authorization", server)

    def test_a_reference_id_selects_the_stored_oauth_registration(self):
        server = server_of(package(oauth_reference_id="abc123"))
        self.assertEqual(server["authorization"], {"type": "OAuthPluginVault", "referenceId": "abc123"})

    def test_another_grunt_address_gets_its_own_id_and_name(self):
        manifest = manifest_of(package(mcp_url=TEST_MCP_URL))
        self.assertNotEqual(manifest["id"], CLOUD_APP_ID)
        self.assertEqual(manifest["name"]["short"], "Grunt (test)")
        self.assertEqual(manifest["agentConnectors"][0]["toolSource"]["remoteMcpServer"]["mcpServerUrl"], TEST_MCP_URL)

    def test_the_address_must_be_https(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(build.BuildError):
                build.build_package(folder, mcp_url="http://localhost:5044/mcp")

    def test_the_tool_list_can_be_left_out(self):
        files = package(tool_description=None)
        self.assertNotIn("tools/grunt-tools.json", files)
        self.assertNotIn("mcpToolDescription", server_of(files))


class SkillRuleTests(unittest.TestCase):
    SKILL = b"---\nname: grunt-demo\ndescription: Use for a demo.\n---\n\n# Demo\n"

    def test_a_valid_skill_passes(self):
        build.check_skill("grunt-demo", {"SKILL.md": self.SKILL, "scripts/run.py": b"print(1)\n"})

    def test_the_name_must_match_the_folder(self):
        with self.assertRaises(build.BuildError):
            build.check_skill("grunt-other", {"SKILL.md": self.SKILL})

    def test_the_name_must_be_kebab_case(self):
        with self.assertRaises(build.BuildError):
            build.check_skill("Grunt_Demo", {"SKILL.md": self.SKILL.replace(b"grunt-demo", b"Grunt_Demo")})

    def test_more_than_twenty_companion_files_are_refused(self):
        files = {"SKILL.md": self.SKILL, **{f"references/{i}.md": b"x" for i in range(21)}}
        with self.assertRaises(build.BuildError):
            build.check_skill("grunt-demo", files)

    def test_file_names_microsoft_365_rejects_are_refused(self):
        for name in ("scripts/con.py", "scripts/a&b.py"):
            with self.assertRaises(build.BuildError, msg=name):
                build.check_skill("grunt-demo", {"SKILL.md": self.SKILL, name: b"x"})


if __name__ == "__main__":
    unittest.main()
