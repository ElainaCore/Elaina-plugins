"""插件市场清单的公共工具: 仓库地址解析与 GitHub API 可用性检查。仅用标准库。"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

MANIFEST_TYPES = {
    'plugins.json': ('complete', 'single'),
    'modules.json': ('module',),
}
REQUIRED_FIELDS = ('name', 'type', 'author', 'description', 'version', 'category', 'github')

API = 'https://api.github.com'
_TOKEN = os.environ.get('GITHUB_TOKEN', '') or os.environ.get('GH_TOKEN', '')


def _api_status(path):
    """请求 GitHub API, 返回 HTTP 状态码 (网络异常返回 0)。"""
    req = urllib.request.Request(f'{API}{path}')
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('User-Agent', 'elaina-plugins-ci')
    if _TOKEN:
        req.add_header('Authorization', f'Bearer {_TOKEN}')
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def parse_repo(github_url):
    """从 github 地址解析出 owner/repo, 解析失败返回 None。"""
    if not github_url:
        return None
    u = github_url.strip().rstrip('/')
    for prefix in ('https://github.com/', 'http://github.com/', 'git@github.com:'):
        if u.startswith(prefix):
            u = u[len(prefix) :]
            break
    if u.endswith('.git'):
        u = u[:-4]
    parts = [p for p in u.split('/') if p]
    if len(parts) >= 2:
        return f'{parts[0]}/{parts[1]}'
    return None


def repo_available(slug):
    """仓库是否存在且可访问 (公开/有权限)。"""
    return _api_status(f'/repos/{slug}') == 200


def branch_available(slug, branch):
    return _api_status(f'/repos/{slug}/branches/{urllib.parse.quote(branch)}') == 200


def path_available(slug, path, branch):
    """仓库内文件或目录是否存在 (按 ref=branch)。"""
    p = urllib.parse.quote(path.strip('/'))
    ref = urllib.parse.quote(branch)
    return _api_status(f'/repos/{slug}/contents/{p}?ref={ref}') == 200


def load_plugins(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def dump_plugins(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
