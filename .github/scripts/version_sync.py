"""同步插件市场清单中的源码版本。

只读取远程仓库源码并做静态解析，不执行远程代码。默认只在远程版本
高于市场版本时更新；无法解析或网络失败时跳过该条目，避免误降级。
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import warnings
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "plugins.json"
REPORT = ROOT / ".github" / "version-report.md"
API = "https://api.github.com"
DEFAULT_SOURCES = (
    "main.py",
    "index.py",
    "app.py",
    "__init__.py",
    "package.json",
    "pyproject.toml",
)
VERSION_RE = re.compile(
    r"^[vV]?(?P<major>0|[1-9][0-9]*)\.(?P<minor>0|[1-9][0-9]*)\.(?P<patch>0|[1-9][0-9]*)"
    r"(?P<suffix>[-+][0-9A-Za-z.-]+)?$"
)
VERSION_LINE_RE = re.compile(
    r"(?im)^\s*[\"']?(?:version|__version__)[\"']?\s*[:=]\s*[\"']([^\"']+)[\"']"
)


@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int
    prerelease: str = ""

    @property
    def key(self):
        # A final release is newer than the same version's prerelease.
        return self.major, self.minor, self.patch, 0 if self.prerelease else 1, self.prerelease


def parse_version(value):
    if not isinstance(value, str):
        return None
    match = VERSION_RE.fullmatch(value.strip())
    if not match:
        return None
    suffix = match.group("suffix") or ""
    return Version(
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
        suffix[1:] if suffix.startswith("-") else "",
    )


def _set_output(**values):
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        return
    with open(output, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def _repo_slug(value):
    value = str(value or "").strip().rstrip("/")
    for prefix in ("https://github.com/", "http://github.com/", "git@github.com:"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    if value.endswith(".git"):
        value = value[:-4]
    parts = [part for part in value.split("/") if part]
    return "/".join(parts[:2]) if len(parts) >= 2 else None


def _source_candidates(entry):
    explicit = str(entry.get("version_source") or "").strip().strip("/")
    if explicit:
        return [explicit]

    path = str(entry.get("path") or "").strip().strip("/")
    if path.lower().endswith((".py", ".json", ".toml")):
        return [path]
    return [f"{path}/{name}" if path else name for name in DEFAULT_SOURCES]


def _github_file(slug, branch, path):
    encoded_path = urllib.parse.quote(path.strip("/"), safe="/")
    encoded_branch = urllib.parse.quote(str(branch or "main"), safe="")
    url = f"https://raw.githubusercontent.com/{slug}/{encoded_branch}/{encoded_path}"
    request = urllib.request.Request(url, headers={
        "User-Agent": "elaina-plugins-version-sync",
    })
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise RuntimeError(f"GitHub raw {error.code} for {slug}:{path}") from error
    except Exception as error:
        raise RuntimeError(f"读取 {slug}:{path} 失败: {error}") from error


def _dict_version(value):
    if not isinstance(value, dict):
        return None
    version = value.get("version")
    return version if parse_version(version) else None


def _python_version(source):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        try:
            tree = ast.parse(source)
        except SyntaxError:
            tree = None
    if tree is not None:
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, ast.Assign):
                targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                targets = [node.target.id]
            if not set(targets) & {"__plugin_meta__", "__module_meta__", "PLUGIN_META", "MODULE_META", "VERSION", "__version__"}:
                continue
            if isinstance(node.value, ast.Dict):
                for key, value in zip(node.value.keys, node.value.values):
                    if isinstance(key, ast.Constant) and key.value == "version" and isinstance(value, ast.Constant):
                        if parse_version(value.value):
                            return value.value
            elif isinstance(node.value, ast.Constant) and parse_version(node.value.value):
                return node.value.value
    match = VERSION_LINE_RE.search(source)
    return match.group(1).strip() if match and parse_version(match.group(1).strip()) else None


def extract_version(source, path):
    suffix = path.lower().rsplit(".", 1)[-1] if "." in path else ""
    if suffix == "py":
        return _python_version(source)
    if suffix == "json":
        try:
            return _dict_version(json.loads(source))
        except (json.JSONDecodeError, TypeError):
            return None
    if suffix == "toml":
        try:
            import tomllib

            data = tomllib.loads(source)
            return _dict_version(data) or _dict_version(data.get("project"))
        except Exception:
            return None
    return None


def discover_version(entry, cache):
    slug = _repo_slug(entry.get("github"))
    if not slug:
        return None, None, "无效仓库地址"
    branch = entry.get("branch") or "main"
    for path in _source_candidates(entry):
        key = (slug, branch, path)
        if key not in cache:
            try:
                cache[key] = _github_file(slug, branch, path)
            except RuntimeError as error:
                return None, None, str(error)
        source = cache[key]
        if source is None:
            continue
        version = extract_version(source, path)
        if version:
            return version, path, None
    return None, None, "未找到可解析的源码版本声明"


def sync_entries(entries, dry_run=False):
    changed = []
    skipped = []
    enabled = []
    for entry in entries:
        name = entry.get("name", "?")
        if entry.get("auto_update_version", True) is False:
            skipped.append(f"- {name}: 已禁用自动版本同步")
            continue
        enabled.append(entry)

    workers = min(8, len(enabled)) or 1
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(lambda entry: discover_version(entry, {}), enabled))

    for entry, (remote, source, error) in zip(enabled, results):
        name = entry.get("name", "?")
        if not remote:
            skipped.append(f"- {name}: {error}")
            continue
        local = parse_version(entry.get("version"))
        remote_parsed = parse_version(remote)
        if local and remote_parsed.key <= local.key:
            skipped.append(f"- {name}: 市场 {entry.get('version')} >= 源码 {remote} ({source})")
            continue
        old = entry.get("version")
        if not dry_run:
            entry["version"] = remote
        changed.append(f"- {name}: {old} -> {remote} ({source})")
    return changed, skipped


def main(argv=None):
    argv = argv or sys.argv[1:]
    dry_run = "--dry-run" in argv
    with open(MANIFEST, encoding="utf-8") as handle:
        entries = json.load(handle)
    changed, skipped = sync_entries(entries, dry_run=dry_run)
    if changed and not dry_run:
        with open(MANIFEST, "w", encoding="utf-8") as handle:
            json.dump(entries, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    report = ["# 插件源码版本同步报告", "", f"模式: {'dry-run' if dry_run else 'write'}", ""]
    report += ["## 已更新", ""] + (changed or ["- 无"])
    report += ["", "## 跳过或无需更新", ""] + (skipped or ["- 无"])
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    _set_output(changed=str(bool(changed)).lower(), count=str(len(changed)))
    print("\n".join(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
