# 发布到 GitHub（可执行清单）

> 本目录（`release/public_v3`）已是**可直接推送**的公开版本：39.9 MB / 2156 个文件，已剔除模型权重、点云样本、数据库、私钥、上传文件、日志与运行时。
> 推送涉及外部写操作，请在终端里执行下面命令（或在 IDE 弹窗中批准）。

---

## 一、先决条件

| 项 | 检查命令 | 说明 |
|----|----------|------|
| Git | `git --version` | 已安装 |
| 代理 | `git config --global --get http.proxy` | 本机系统代理为 `127.0.0.1:10090`，git 需要单独配置（见下） |
| 凭据 | Windows 凭据管理器中的 `git:https://github.com` | 若失效，`git push` 会提示登录；建议用 PAT（勾选 `repo`） |

配置代理（本机实测必需，否则 `github.com:443` 超时）：

```bash
git config --global http.proxy http://127.0.0.1:10090
git config --global https.proxy http://127.0.0.1:10090
```

---

## 二、方式 1：推到已有仓库的新分支（不改动 main，最安全）

已有公开仓库：`https://github.com/chenshi0504/zhixinyoukong-platform`（当前 main 为 1 次提交的旧快照）。

```bash
cd "D:\chenshi\智信优控_面向车路云一体化的综合交通实验平台\release\public_v3"

git init
git add .
git commit -m "docs+src: 公开发布版（源码/文档/部署配置，剔除权重与敏感文件）"

git remote add origin https://github.com/chenshi0504/zhixinyoukong-platform.git
git branch -M release/public
git push -u origin release/public
```

推送成功后：
- 仓库多出 `release/public` 分支，main 不受影响；
- 在 GitHub 仓库页 **Compare & pull request** → 合并到 main（确认无误后再合并）；
- 或直接 Settings → Branches → 把默认分支改为 `release/public`（不推荐长期如此）。

> 若希望**直接替换 main**（会覆盖旧快照），需 `git push -f origin release/public:main`——这是破坏性操作，请自行确认后再执行。

## 三、方式 2：新建独立仓库

Web：<https://github.com/new> → 名称如 `zhixinyoukong-platform-public`，**Public**，不要勾选任何初始化文件。

```bash
git init
git add .
git commit -m "init: 智信优控平台公开发布版"
git remote add origin https://github.com/<你的账号>/zhixinyoukong-platform-public.git
git branch -M main
git push -u origin main
```

或用 GitHub CLI（本机未安装，`winget install GitHub.cli` 后使用）：

```bash
gh auth login
gh repo create zhixinyoukong-platform-public --public --source=. --push
```

---

## 四、开启 GitHub Pages（文档站）

本目录已内置 workflow：`.github/workflows/pages.yml`（把 `site/` 发布为 Pages）。

1. 推送后进入仓库 **Settings → Pages**
2. **Source** 选择 **GitHub Actions**（不要选 Deploy from a branch）
3. 回到 **Actions** 页，等待 `Deploy docs site` 运行完成
4. 访问 `https://<账号>.github.io/<仓库名>/`

备选（不用 Actions）：把 `site/` 目录内容推到 `gh-pages` 分支，然后在 Pages 里选择 `gh-pages` 分支 `/ (root)`：

```bash
git subtree push --prefix site origin gh-pages
```

> 说明：Pages 只能托管静态内容。学生打开文档站可以看到介绍、手册与截图；要真正登录做实验，仍需按 `deploy/README.md` 部署后端。

---

## 五、首次推送常见问题

| 现象 | 原因 | 处理 |
|------|------|------|
| `Failed to connect to github.com port 443` | git 未走代理 | 执行第二节的两条 `git config` 命令 |
| `remote: Support for password authentication was removed` | 用了账号密码 | 改用 PAT（Settings → Developer settings → Personal access tokens） |
| `GH001: Large files detected` | 单文件 >100 MB | 本版本已剔除；若自行添加请用 Git LFS |
| `Updates were rejected` | 远端有新提交 | 先 `git pull --rebase origin <分支>`，勿强推 main |
| Actions 里 Pages 部署失败 | Pages 未设为 GitHub Actions | 按第四节第 2 步设置后重跑 |

---

## 六、推送前最后自检

```bash
git status --porcelain | Measure-Object -Line      # 应只包含预期文件
git ls-files | Select-String -Pattern '\.(pem|env|db|pt|pcd|weights)$'   # 应为空
```

本目录已包含 `_excluded_large_files.txt`（记录被剔除的大文件清单，可按需删除）。
