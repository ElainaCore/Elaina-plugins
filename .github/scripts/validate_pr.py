"""校验 PR 中的插件清单 (plugins.json / onebot_plugins.json): 格式 + schema + 新增/改动条目的仓库可用性。

用法: python validate_pr.py <head.json> [base.json] [清单名]

- head: PR 改动后的清单 (必填)
- base: 目标分支的清单 (选填); 提供后只对新增/改动的条目做仓库可达性检查

产物:
- 写出 .github/pr-report.md 作为 PR 评论正文。
- 通过 $GITHUB_OUTPUT 暴露 ok (true/false)。
- 校验不通过时以非零状态码退出。
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (  # noqa: E402
    ALLOWED_TYPES,
    REQUIRED_FIELDS,
    branch_available,
    parse_repo,
    path_available,
    repo_available,
)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPORT = os.path.join(ROOT, '.github', 'pr-report.md')


def _set_output(**kw):
    out = os.environ.get('GITHUB_OUTPUT')
    if not out:
        return
    with open(out, 'a', encoding='utf-8') as f:
        for k, v in kw.items():
            f.write(f'{k}={v}\n')


def _load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def validate_schema(data):
    """返回错误信息列表 (空列表代表通过)。"""
    errors = []
    if not isinstance(data, list):
        return ['清单顶层必须是数组']
    seen = set()
    for i, e in enumerate(data):
        tag = f'第 {i + 1} 项'
        if not isinstance(e, dict):
            errors.append(f'{tag}: 必须是对象')
            continue
        name = e.get('name', '')
        if name:
            tag = f'`{name}`'
        for k in REQUIRED_FIELDS:
            if not e.get(k):
                errors.append(f'{tag}: 缺少必填字段 `{k}`')
        t = e.get('type', '')
        if t and t not in ALLOWED_TYPES:
            errors.append(f'{tag}: type 非法 `{t}` (只能是 {"/".join(ALLOWED_TYPES)})')
        if 'alone' in e and not isinstance(e['alone'], bool):
            errors.append(f'{tag}: alone 必须是布尔值')
        if 'tags' in e and not (isinstance(e['tags'], list) and all(isinstance(x, str) for x in e['tags'])):
            errors.append(f'{tag}: tags 必须是字符串数组')
        if e.get('github') and parse_repo(e['github']) is None:
            errors.append(f'{tag}: github 不是合法的仓库地址')
        if name:
            if name in seen:
                errors.append(f'{tag}: name 重复')
            seen.add(name)
    return errors


def _key(e):
    return json.dumps(e, sort_keys=True, ensure_ascii=False)


def _owner(entry):
    """返回条目 github 仓库的 owner (小写), 无法解析时返回 None。"""
    slug = parse_repo(entry.get('github', '')) if isinstance(entry, dict) else None
    return slug.split('/')[0].lower() if slug else None


def validate_ownership(head, base, author):
    """PR 作者只能新增/修改/删除属于自己仓库的插件条目。返回错误列表。"""
    errors = []
    author = (author or '').lower()
    base_by_name = {e.get('name'): e for e in (base or []) if isinstance(e, dict) and e.get('name')}
    head_by_name = {e.get('name'): e for e in head if isinstance(e, dict) and e.get('name')}

    for name, e in head_by_name.items():
        old = base_by_name.get(name)
        if old is None:
            if _owner(e) != author:
                errors.append(f'`{name}`: 新增插件的仓库必须属于 PR 作者 `{author}` (当前 owner: `{_owner(e)}`)')
        elif _key(old) != _key(e):
            if _owner(old) != author:
                errors.append(f'`{name}`: 无权修改属于 `{_owner(old)}` 的插件条目')
            elif _owner(e) != author:
                errors.append(f'`{name}`: 不允许将插件仓库转移给其他用户 (`{_owner(e)}`)')
    for name, old in base_by_name.items():
        if name not in head_by_name and _owner(old) != author:
            errors.append(f'`{name}`: 无权删除属于 `{_owner(old)}` 的插件条目')
    return errors


def validate_order(head, base):
    """新插件只能追加到末尾, 且不允许重排已有插件。返回错误列表。"""
    base_names = [e.get('name') for e in (base or []) if isinstance(e, dict) and e.get('name')]
    head_names = [e.get('name') for e in head if isinstance(e, dict) and e.get('name')]
    base_set, head_set = set(base_names), set(head_names)
    expected = [n for n in base_names if n in head_set] + [n for n in head_names if n not in base_set]
    if head_names == expected:
        return []
    errors = []
    kept = [n for n in head_names if n in base_set]
    if kept != [n for n in base_names if n in head_set]:
        errors.append('不允许调整已有插件的顺序')
    last_kept_idx = max((head_names.index(n) for n in kept), default=-1)
    misplaced = [n for n in head_names if n not in base_set and head_names.index(n) < last_kept_idx]
    for n in misplaced:
        errors.append(f'`{n}`: 新插件只能追加到列表末尾, 不允许插入到已有插件之前')
    return errors


def changed_entries(head, base):
    """返回 head 中相对 base 新增或改动的条目。"""
    if base is None:
        return list(head)
    base_keys = {_key(e) for e in base if isinstance(e, dict)}
    return [e for e in head if isinstance(e, dict) and _key(e) not in base_keys]


def check_availability(entry):
    """检查单个条目的仓库/分支/路径可用性, 返回 (ok, messages)。"""
    name = entry.get('name', '?')
    slug = parse_repo(entry.get('github', ''))
    if not slug:
        return False, [f'`{name}`: 无法解析仓库地址']
    branch = entry.get('branch', 'main')
    msgs = []
    if not repo_available(slug):
        return False, [f'`{name}`: 仓库 `{slug}` 不可访问 (不存在或非公开)']
    if not branch_available(slug, branch):
        return False, [f'`{name}`: 仓库 `{slug}` 不存在分支 `{branch}`']

    ok = True
    targets = [entry['path']] if entry.get('path') else []
    for t in targets:
        if path_available(slug, t, branch):
            continue
        # path 指向子目录下的文件时, 退一步检查其父目录是否存在
        parent = t.strip('/').rsplit('/', 1)[0] if '/' in t.strip('/') else ''
        if parent and path_available(slug, parent, branch):
            continue
        ok = False
        msgs.append(f'`{name}`: 仓库内路径不存在 `{t}` (ref `{branch}`)')
    if ok and not msgs:
        msgs.append(f'`{name}`: 仓库 `{slug}@{branch}` 可访问 ✓')
    return ok, msgs


def main():
    head_path = sys.argv[1]
    base_path = sys.argv[2] if len(sys.argv) > 2 and os.path.exists(sys.argv[2]) else None
    label = sys.argv[3] if len(sys.argv) > 3 else 'plugins.json'

    lines = [f'## 🤖 插件清单自动校验 — `{label}`', '']
    overall_ok = True

    # 1) JSON 解析
    try:
        head = _load(head_path)
    except Exception as e:
        lines += ['### ❌ JSON 解析失败', '', f'```\n{e}\n```', '', '请检查 plugins.json 是否为合法 JSON (逗号/引号/括号)。']
        with open(REPORT, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        _set_output(ok='false')
        print('\n'.join(lines))
        sys.exit(1)

    base = None
    if base_path:
        try:
            base = _load(base_path)
        except Exception:
            base = None

    # 2) schema
    errors = validate_schema(head)

    # 2.5) 顺序与归属校验 (仅在 schema 通过且有 base 可比对时)
    if not errors and base is not None:
        errors += validate_order(head, base)
        author = os.environ.get('PR_AUTHOR', '')
        perm = os.environ.get('PR_AUTHOR_PERM', '').lower()
        if author and perm not in ('admin', 'maintain', 'write'):
            errors += validate_ownership(head, base, author)

    if errors:
        overall_ok = False
        lines.append('### ❌ 校验未通过')
        lines += [f'- {e}' for e in errors]
        lines.append('')
    else:
        lines.append('### ✅ JSON 格式与字段校验通过')
        lines.append('')

    # 3) 仓库可用性 (仅新增/改动条目)
    targets = changed_entries(head, base) if not errors else []
    if targets:
        lines.append('### 🔗 新增/改动插件的仓库可用性')
        for e in targets:
            ok, msgs = check_availability(e)
            overall_ok = overall_ok and ok
            lines += [f'- {m}' for m in msgs]
        lines.append('')
    elif not errors:
        lines.append('_本次无新增/改动的插件条目需要做仓库检查。_')
        lines.append('')

    lines.append('---')
    lines.append('✅ 全部通过，符合自动合并条件。' if overall_ok else '❌ 存在问题，需修复后才能合并。')

    with open(REPORT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    _set_output(ok='true' if overall_ok else 'false')
    print('\n'.join(lines))
    sys.exit(0 if overall_ok else 1)


if __name__ == '__main__':
    main()
