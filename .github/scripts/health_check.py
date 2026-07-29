"""每日检查插件清单 (plugins.json / onebot_plugins.json) 中各插件仓库是否可访问。

- 首次检测到某仓库不可访问: 记录失败时间并告警。
- 持续不可访问超过宽限期 (默认 24 小时): 自动删除该仓库对应的所有插件索引。
- 仓库恢复: 清除其失败记录。

产物:
- 原地更新各插件清单 (若有删除) 与状态文件 .github/health-state.json。
- 写出 .github/health-report.md 作为告警 Issue 正文。
- 通过 $GITHUB_OUTPUT 暴露 has_alert / changed 供 workflow 判断。
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import dump_plugins, load_plugins, parse_repo, repo_available  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MANIFESTS = [os.path.join(ROOT, 'plugins.json'), os.path.join(ROOT, 'onebot_plugins.json')]
STATE = os.path.join(ROOT, '.github', 'health-state.json')
REPORT = os.path.join(ROOT, '.github', 'health-report.md')

GRACE_HOURS = float(os.environ.get('GRACE_HOURS', '24'))


def _load_state():
    if os.path.exists(STATE):
        try:
            with open(STATE, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_state(state):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write('\n')


def _set_output(**kw):
    out = os.environ.get('GITHUB_OUTPUT')
    if not out:
        return
    with open(out, 'a', encoding='utf-8') as f:
        for k, v in kw.items():
            f.write(f'{k}={v}\n')


def _fmt(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime('%Y-%m-%d %H:%M UTC')


def main():
    manifests = {path: load_plugins(path) for path in MANIFESTS if os.path.exists(path)}
    state = _load_state()
    now = time.time()

    # 仓库 -> 该仓库下的插件名列表 (汇总所有清单)
    repo_to_names = {}
    for plugins in manifests.values():
        for p in plugins:
            slug = parse_repo(p.get('github', ''))
            if slug:
                repo_to_names.setdefault(slug, []).append(p.get('name', '?'))

    newly_failed, still_failing, recovered, to_delete = [], [], [], []

    for slug, names in sorted(repo_to_names.items()):
        if repo_available(slug):
            if slug in state:
                recovered.append(slug)
                state.pop(slug, None)
            continue
        # 不可访问
        first = state.get(slug)
        if first is None:
            state[slug] = now
            newly_failed.append((slug, names))
        else:
            elapsed_h = (now - float(first)) / 3600.0
            if elapsed_h >= GRACE_HOURS:
                to_delete.append((slug, names, first))
            else:
                still_failing.append((slug, names, first, elapsed_h))

    # 删除超期仓库的插件索引
    deleted_slugs = {s for s, _, _ in to_delete}
    changed = False
    if deleted_slugs:
        for path, plugins in manifests.items():
            kept = [p for p in plugins if parse_repo(p.get('github', '')) not in deleted_slugs]
            if len(kept) != len(plugins):
                dump_plugins(path, kept)
                changed = True
        for s in deleted_slugs:
            state.pop(s, None)

    _save_state(state)

    # active: 仍有未解决的问题 (新失败/宽限期内); notify: 本次有任何值得通报的事
    active = bool(newly_failed or still_failing)
    notify = bool(newly_failed or still_failing or to_delete or recovered)

    def _owner(slug):
        return slug.split('/')[0]

    # 生成告警正文 (@ 失效仓库的作者, 即该仓库的 GitHub owner)
    lines = ['## 🔴 插件仓库可用性告警', '', f'检查时间: {_fmt(now)}', '']
    if to_delete:
        lines.append(f'### ⛔ 已自动移除 (不可访问超过 {GRACE_HOURS:g} 小时)')
        for slug, names, first in to_delete:
            lines.append(f'- `{slug}` (@{_owner(slug)}) — 自 {_fmt(float(first))} 起不可访问，已移除插件: {", ".join(names)}')
        lines.append('')
    if newly_failed:
        lines.append('### ⚠️ 首次检测到不可访问')
        for slug, names in newly_failed:
            lines.append(f'- `{slug}` (@{_owner(slug)}) — 涉及插件: {", ".join(names)}（请尽快恢复仓库访问；若约 {GRACE_HOURS:g} 小时后仍不可访问将自动移除）')
        lines.append('')
    if still_failing:
        lines.append('### ⏳ 仍不可访问 (宽限期内)')
        for slug, names, first, elapsed_h in still_failing:
            remain = max(0.0, GRACE_HOURS - elapsed_h)
            lines.append(f'- `{slug}` (@{_owner(slug)}) — 自 {_fmt(float(first))} 起不可访问，已 {elapsed_h:.1f}h，约 {remain:.1f}h 后移除。插件: {", ".join(names)}')
        lines.append('')
    if recovered:
        lines.append('### ✅ 本次已恢复')
        for slug in recovered:
            lines.append(f'- `{slug}`')
        lines.append('')
    if not notify:
        lines = ['所有插件仓库均可访问。']

    with open(REPORT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    _set_output(
        notify=str(notify).lower(),
        active=str(active).lower(),
        changed=str(changed).lower(),
    )

    print('\n'.join(lines))
    print(f'\n[health] newly_failed={len(newly_failed)} still_failing={len(still_failing)} '
          f'deleted_repos={len(deleted_slugs)} recovered={len(recovered)} changed={changed}')


if __name__ == '__main__':
    main()
