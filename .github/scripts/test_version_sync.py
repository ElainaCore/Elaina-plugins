import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import version_sync


class VersionSyncTests(unittest.TestCase):
    def test_parse_version_orders_final_after_prerelease(self):
        prerelease = version_sync.parse_version("v1.2.3-rc.1")
        final = version_sync.parse_version("1.2.3")
        self.assertIsNotNone(prerelease)
        self.assertGreater(final.key, prerelease.key)
        self.assertIsNone(version_sync.parse_version("1.2"))

    def test_extracts_static_python_metadata_without_execution(self):
        source = "raise RuntimeError('must not run')\n__plugin_meta__ = {'version': '2.4.1'}\n"
        self.assertEqual(version_sync.extract_version(source, "main.py"), "2.4.1")

    def test_extracts_json_and_toml_versions(self):
        self.assertEqual(
            version_sync.extract_version('{"version": "1.4.0"}', "package.json"),
            "1.4.0",
        )
        self.assertEqual(
            version_sync.extract_version('[project]\nversion = "3.2.1"\n', "pyproject.toml"),
            "3.2.1",
        )

    def test_source_candidates_support_explicit_override(self):
        self.assertEqual(
            version_sync._source_candidates({"version_source": "app/constants.py"}),
            ["app/constants.py"],
        )
        self.assertEqual(
            version_sync._source_candidates({"path": "plugin/main.py"}),
            ["plugin/main.py"],
        )

    def test_sync_only_upgrades_and_honors_opt_out(self):
        entries = [
            {"name": "upgrade", "version": "1.0.0", "github": "https://github.com/a/b"},
            {"name": "newer-market", "version": "3.0.0", "github": "https://github.com/a/c"},
            {
                "name": "disabled",
                "version": "1.0.0",
                "github": "https://github.com/a/d",
                "auto_update_version": False,
            },
        ]

        def discover(entry, cache):
            versions = {"upgrade": "1.0.1", "newer-market": "2.9.9"}
            return versions[entry["name"]], "main.py", None

        with mock.patch.object(version_sync, "discover_version", side_effect=discover) as mocked:
            changed, skipped = version_sync.sync_entries(entries)

        self.assertEqual(entries[0]["version"], "1.0.1")
        self.assertEqual(entries[1]["version"], "3.0.0")
        self.assertEqual(entries[2]["version"], "1.0.0")
        self.assertEqual(len(changed), 1)
        self.assertTrue(any("已禁用" in line for line in skipped))
        self.assertEqual(mocked.call_count, 2)


if __name__ == "__main__":
    unittest.main()
