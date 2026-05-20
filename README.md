# 番茄发文助手

## 环境准备

```bash
pip install -r requirements.txt
playwright install chromium
```

## 快速开始

```bash
# 1. 启动 GUI
python3 main_webview.py
```

首次进入后，如果程序检测不到有效登录凭证，会在界面内提示登录并获取 `data/state.json`。
`python3 login.py` 仅作为手动登录入口保留，不再是默认必经步骤。

## 运行入口

- GUI 主程序：`python3 main_webview.py`
- 登录凭证获取：`python3 login.py`

详细使用方式见：

- [docs/使用说明.md](/Users/jiangmiao/work_dict/aicode/fanqieAutoPublish/docs/使用说明.md)

## 目录结构

```text
fanqieAutoPublish/
  app/
    login_flow.py
    main_webview.py
    paths.py
    web/
  assets/
    logo.ico
  data/
    state.json
    config.json
  docs/
    使用说明.md
  scripts/
    build_windows.bat
  login.py
  main_webview.py
  requirements.txt
```

## 说明

- `app/`：正式业务代码与前端静态资源
- `assets/`：图标等打包资源
- `data/`：运行期配置和登录凭证
- `docs/`：用户文档
- `scripts/`：打包脚本

测试脚本、抓包脚本、PoC 脚本和临时调试产物已从正式版本中移除。
