<div align="center">

# Elaina-plugins

ElainaBot 官方插件与模块市场 — 在这里发现和分享插件/模块

[![ElainaBot](https://img.shields.io/badge/框架-ElainaBot_v2-blue)](https://github.com/ElainaCore/ElainaBot_v2)
[![QQ群](https://img.shields.io/badge/QQ交流群-1085402468-blue)](https://qm.qq.com/q/5O3xGoe4so)

</div>

## 🔌 如何提交插件

### 第一步：准备你的插件仓库

插件分为两种类型，由 `plugins.json` 的 `type` 字段**显式声明**（不再依据是否有 `path` 推断）：

**完整插件 `complete`** (含入口文件 `main.py`/`index.py`/`app.py`，安装到 `plugins/<name>/`)：
```
你的仓库/
├── main.py              # 入口文件 (必须)
├── app/                 # 子模块目录
│   ├── feature_a.py
│   └── feature_b.py
├── data/                # 数据目录 (可选)
└── requirements.txt     # 额外依赖 (可选)
```
> 一个仓库内可放多个完整插件，每个插件各占一个子目录，用 `path` 指向子目录分别提交。

**独立插件 `single`** (无入口文件，可单文件或多文件)：
```
你的仓库/
├── my_plugin.py         # 插件文件
└── panel.html           # 附属文件 (html 等, 可选)
```
> 独立插件默认下载**单文件**到共享目录 `plugins/alone/<name>.py`；若插件需要附带 html 等多文件，请声明 `"alone": false`，安装时会装到**专属目录** `plugins/<name>/`，避免不同插件的同名文件互相覆盖。

### 第二步：添加插件元数据

在入口文件中声明 `__plugin_meta__`：

```python
__plugin_meta__ = {
    'name': '我的插件',
    'author': '你的名字',
    'description': '插件功能描述',
    'version': '1.0.0',
    'github': 'https://github.com/你的用户名/你的仓库',
}
```

### 第三步：提交 PR

1. Fork 本仓库
2. 编辑 `plugins.json`，添加你的插件信息
3. 提交 Pull Request

### `plugins.json` 格式

```json
[
  {
    "name": "插件目录名",
    "type": "complete",
    "author": "作者",
    "description": "插件描述",
    "version": "1.0.0",
    "category": "分类",
    "github": "https://github.com/你的用户名/你的仓库",
    "branch": "main",
    "tags": ["标签1", "标签2"]
  }
]
```

#### 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | ✅ | 名称, 安装后的目录名 (`plugins/<name>` 或 `modules/<name>`) |
| `type` | ✅ | 类型: `complete` (完整插件) / `single` (独立插件) / `module` (模块) |
| `author` | ✅ | 作者名 |
| `description` | ✅ | 描述 |
| `version` | ✅ | 版本号 |
| `category` | ✅ | 分类 |
| `github` | ✅ | GitHub 仓库地址 |
| `branch` | ❌ | 分支名，默认 `main` |
| `path` | ❌ | 仓库内路径 (字符串)：一个文件，或一个子目录。指向子目录时会下载该目录下**全部**文件 (含 html 等附属文件)。`complete` 用它选一仓多插件里的某个子目录；`single` 用它指向单文件或其所在子目录 |
| `alone` | ❌ | `single` 专用：默认 `true` 装到共享 `plugins/alone/<name>.py` (仅单文件)；显式 `false` 时装到专属目录 `plugins/<name>/` (支持多文件，用 `path` 指向子目录整目录下载) |
| `tags` | ❌ | 标签数组，用于搜索 |

> **独立插件要下多个文件 (如 .py + .html)？** 把这几个文件放进仓库的同一个子目录，然后 `alone: false` + `path` 指向该子目录 (或目录下任一文件)，安装时整个子目录会一起下到 `plugins/<name>/`。

#### 安装模式示例

**完整插件 (整仓库)** — 解压整个仓库到 `plugins/<name>/`：
```json
{
  "name": "my-plugin",
  "type": "complete",
  "github": "https://github.com/user/my-plugin",
  "branch": "main"
}
```

**完整插件 (一仓多插件)** — 用 `path` 指向子目录，只解压该子目录到 `plugins/<name>/`：
```json
{
  "name": "插件A",
  "type": "complete",
  "github": "https://github.com/user/multi-plugins",
  "path": "pluginA",
  "branch": "main"
}
```

**独立插件 (单文件, 共享目录)** — 下载单个 `.py` 到 `plugins/alone/<name>.py`：
```json
{
  "name": "hello",
  "type": "single",
  "github": "https://github.com/user/mini-plugins",
  "path": "hello.py",
  "branch": "main"
}
```

**独立插件 (多文件, 专属目录)** — 带 html 等附属文件，声明 `alone: false`，装到 `plugins/<name>/` (同目录文件一并下载)：
```json
{
  "name": "my-plugin",
  "type": "single",
  "github": "https://github.com/user/mini-plugins",
  "path": "my-plugin/my_plugin.py",
  "alone": false,
  "branch": "main"
}
```
> 上例会把仓库里 `my-plugin/` 目录下的所有文件 (`.py` + `panel.html` 等) 一起装到 `plugins/my-plugin/`。
>
> 注意：若插件的 `.py` 通过相对路径引用了仓库内**子目录之外**的共享文件 (如 `../_shared/xxx.py`)，子目录提取不会带上这些文件，插件会无法运行——这类插件请用 `complete` 整仓库安装。

## 📦 如何提交模块

### 第一步：准备你的模块仓库

模块是一个独立的 GitHub 仓库，结构如下：

```
你的仓库/
├── main.py              # 入口文件 (必须)
├── app/                 # 子模块目录 (可选)
├── data/                # 数据目录 (可选, 更新时保留)
└── requirements.txt     # 额外依赖 (可选)
```

### 第二步：添加模块元数据

在 `main.py` 中声明 `__module_meta__`：

```python
__module_meta__ = {
    'name': '模块名',
    'description': '模块描述',
    'version': '1.0.0',
    'author': '作者',
}
```

### 第三步：提交 PR

1. Fork 本仓库
2. 编辑 `plugins.json`，添加你的模块信息
3. 提交 Pull Request

```json
{
  "name": "my_module",
  "type": "module",
  "author": "你的名字",
  "description": "模块描述",
  "version": "1.0.0",
  "category": "分类",
  "github": "https://github.com/你的用户名/你的仓库",
  "branch": "main",
  "tags": ["标签1"]
}
```

> 安装时整个仓库内容会解压到 `modules/<name>/`，`data/` 目录在更新时不会被覆盖。

## 📋 提交规范

- 额外 pip 依赖请在仓库中提供 `requirements.txt`
- 插件代码必须包含 `__plugin_meta__`，模块必须包含 `__module_meta__`
- PR 只能新增/修改/删除**属于你自己 GitHub 账号仓库**的插件条目，不能改动他人的条目
- 新插件请**追加到清单末尾**（`plugins.json` / `onebot_plugins.json`），不要插入到已有插件之间，也不要调整已有插件顺序
- 自动合并仅在 PR 只改动 `plugins.json` / `onebot_plugins.json` 时生效；改动其他文件需人工审核
- 禁止提交恶意代码、违法内容

