# auto-comfy-draw

[中文](README.md) | [English](README.en.md)

<p>
  <img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-green.svg">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.7%2B-blue.svg">
  <img alt="Backend: ComfyUI" src="https://img.shields.io/badge/Backend-ComfyUI-8A2BE2.svg">
</p>

一个 **agent skill**，用来驱动本地或远程的 **ComfyUI**，做**文生图 / 图生图**。

你只需描述想要的画面，这个 skill 会帮你配好 ComfyUI 工作流、写好 prompt、批量出图并返回成品。**配置驱动、内容中立**——prompt 想写什么完全由你决定。

## 怎么对 agent 开口（推荐 prompt）

用户**只对话，不用敲任何命令行**。`--discover` / `--scaffold` 等命令由 agent 在底层执行。你可以直接说：

- "帮我画一张傍晚的城市天际线"
- "用 waiIllustriousSDXL 和 xxx LoRA 画一只猫在屋顶，输出到 D:/my_imgs，出 4 张"
- "把这张 ref.png 改得更写实一点"（img2img）
- "换个种子 / 再来 4 张 / 加点细节"

| 你说的话 | agent 会做 |
|---|---|
| "帮我画一张 <描述>"（首次） | 扫描可用模型 → 问你模型/LoRA/输出/是否垫图 → 生成配置 → 自检 → 出图 |
| "用 <模型> <lora> 画 <描述>" | 直接生成配置，用你的描述跑图 |
| "把这张图改成 <风格>" | 图生图（`--init` + `--denoise`） |
| "换个种子 / 加细节" | 调 `--seed-basis` / `--count` 重跑 |

> 描述得越清楚（主体 / 风格 / 构图 / 是否垫图），出图越贴近你想要；不用记任何命令行。

**示例输出**（由本流水线生成）：

![example output](examples/example_output.png)

---

## 这是什么

- **`SKILL.md`** — skill 入口（frontmatter `name`/`description`）。由你的 agent 加载，让它知道怎么搭建工作流、替你生成 prompt。
- **`pipeline.py`** — 与 harness 无关的 Python 驱动。读取配置 JSON，提交 txt2img/img2img 任务，轮询 ComfyUI，下载结果，并上报错误。
- **`AGENTS.md`** — 面向会自动读取工作目录 `AGENTS.md` 的 harness 的同一套流程。

## 环境要求

- Python 3.7+
- 一个在运行的 **ComfyUI**（本地或远程），并已装好你的模型 / LoRA。
- `pipeline.py` 只调用 ComfyUI 的 HTTP API（`/prompt`、`/queue`、`/history`、`/view`），无其他依赖。

## 安装为 agent skill

本仓库以 **`SKILL.md`** skill 的形式打包，"安装"取决于你 agent 的 skill 机制：

1. **DSH / Anthropic 兼容 loader** — 把这个仓库（或只需 `SKILL.md` + `pipeline.py` + `config.example.json`）放进你 harness 扫描 skill 的目录。`SKILL.md` 的 frontmatter（`name: auto-comfy-draw`、`description`）就是注册入口，agent 会据此匹配请求。
2. **会自动读取 `AGENTS.md` 的 harness** — 把本仓库的 `AGENTS.md` 拷到你的项目/工作区根目录；它会自动注入 agent 上下文，指示 agent 使用这套流程。
3. **直接当 CLI 用** — `pipeline.py` 本身是个命令行工具，不依赖任何 agent 也能跑。

> 具体的 skill 目录路径因 harness 而异——请查阅你所用 agent 的文档，确认 `SKILL.md` 从哪里加载。
> 本仓库已 gitignore `config*.json`（仅保留 `config.example.json`），你的真实配置留在本地。

## 快速开始

```bash
# 1. 看看 ComfyUI 实际能用什么
python pipeline.py --discover

# 2. 根据你的选择生成配置（模型 / LoRA / 输出目录）
python pipeline.py --scaffold --model sdxl_foo.safetensors --lora bar.safetensors \
    --output-dir D:/my_imgs --name demo --config config.demo.json

# 3. 自检（ComfyUI 可达？模型在不在？输出目录可写？）
python pipeline.py --check --config config.demo.json

# 4. 出图
python pipeline.py --config config.demo.json --prompt "a city at dusk" --count 4
```

## 命令

| 模式 | 作用 |
|---|---|
| `--discover` | 列出 ComfyUI 当前暴露的底模与 LoRA。 |
| `--scaffold --model <m> [--lora <l>] --output-dir <dir> [--name <n>] [--config <c>] [--prompts "a\|b"]` | 写出配置 JSON。 |
| `--check [--config c]` | 自检（ComfyUI 可达、模型存在、输出目录可写）。 |
| `--start [--start-cmd "<cmd>"]` | 拉起 ComfyUI 并等待就绪（**仅在征得用户同意后**）。 |
| `--config c --count N [--prompt ...] [--names a,b] [--init ref.png --denoise 0.6] [--seed-basis N] [--host/--port]` | 批量出图。 |

批量行为：探活端口(8188/8189) → 全部入队 → 轮询 `/queue` + `/history/<pid>` → 下载到 `output_dir` → 失败/超时**非零退出**。取消批量：`POST /queue {"clear": true}`。

## Prompt 与配置

`--prompt` 接收 prompt 字符串；**多个 prompt 用 `|` 分隔**。`--names a,b` 跑配置里的命名 prompt。

`config.example.json` 字段：`name`、`model`、`lora`/`lora_strength`、`positive`、`negative`、`width/height`、`steps/cfg/sampler/scheduler/denoise`、`start_cmd`、`output_dir`、`prefix`、`prompts`。

- **图生图**：`--init <basename>` + `--denoise N`（把参考图放进 ComfyUI 的 `input` 目录）。
- **可复现**：`--seed-basis N` → 每个 prompt 种子 = `N + 序号*100000 + k`。
- **远程**：`--host/--port` 指向转发/隧道后的 ComfyUI，结果会拉回 `output_dir`。

## 自动启动 ComfyUI（需经同意）

如果 ComfyUI 没在运行，`--discover`/`--check` 会给出明确报错。你可以**让 agent 帮你启动**，但**必须先经你同意**：

- 先征求同意；你同意后执行 `python pipeline.py --start --start-cmd "<comfyui 启动命令>"`（或在配置里设 `start_cmd`）。它最多等待 120 秒轮询 `/system_stats`。
- agent **绝不会在未经你同意时自动启动**；你不同意或启动失败时，就自己启动 ComfyUI 再重跑。

## License

MIT（见 `LICENSE`）。本仓库仅含工具/文档，不含任何生成的图像或第三方素材。

## 示例输出

可在 [examples/example_output.png](examples/example_output.png) 查看由本流水线生成的一张示例图。
