# auto-comfy-draw · ComfyUI 一键绘图助手

<p>
  <img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-green.svg">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.7%2B-blue.svg">
  <img alt="Backend: ComfyUI" src="https://img.shields.io/badge/Backend-ComfyUI-8A2BE2.svg">
</p>

> 无须配置复杂工作流/设计提示词，用自然语言搭建属于你的AI绘图方案：**扫描可用模型/LoRA + 配好工作流 + 写好 prompt + 一键批量出图**。不用手搓复杂提示词，也不用改配置 JSON。

![示例输出](examples/example_output.png)

## 第一次用（三步就绪）

**1. 扫描可用资源**
```bash
python pipeline.py --discover
```
列出 ComfyUI 当前能用的底模和 LoRA。发现缺模型？重启 ComfyUI 再试。

**2. 告诉auto-comfy-draw**：用哪个底模、要不要 LoRA、输出到哪、想要什么画面。它据此生成配置：
```bash
python pipeline.py --scaffold --model sdxl_foo.safetensors --lora bar.safetensors \
    --output-dir D:/my_imgs --name demo --config config.demo.json
```

**3. 自检 + 开跑**
```bash
python pipeline.py --check --config config.demo.json        # 模型在不在 / 目录可写
python pipeline.py --config config.demo.json --prompt "a city at dusk" --count 4
```

## 手动调用（进阶）

```bash
# 跑配置里所有命名 prompts × 3
python pipeline.py --config config.json --count 3

# 直接给 prompt × 4（多 prompt 用 | 分隔）
python pipeline.py --config config.json --prompt "a cat on a roof|a dog in a park" --count 4

# 图生图（参考图放进 ComfyUI input 目录）
python pipeline.py --config config.json --init ref.png --denoise 0.6 --count 4

# 可复现 / 远程
python pipeline.py --config config.json --seed-basis 123456 --count 4
python pipeline.py --config config.json --host 192.168.1.10 --port 8188 --prompt "..." --count 4
```

脚本行为：探测端口(8188/8189) → 批量入队 → 轮询 `/queue`、`/history/<pid>` → 下载到 `output_dir` → 失败/超时**非零退出**。取消批量：`POST /queue {"clear": true}`。

## ComfyUI 没启动？
- 先提醒用户"ComfyUI 还没启动"，然后**征求同意**是否要帮你拉起。
- 同意 → `python pipeline.py --start --start-cmd '<启动命令>'`（或读配置 `start_cmd`），等待就绪。
- 不同意 / 启动失败 → 让用户自己启动（Desktop 或 `python main.py`）再继续。
- **绝不未经同意就自动启动**。

## 命令一览
| 命令 | 作用 |
|---|---|
| `--discover` | 列出可用底模 & LoRA |
| `--scaffold --model .. --output-dir .. [--lora ..] [--name ..] [--config ..] [--prompts "a\|b"]` | 生成配置 |
| `--check [--config c]` | 自检（ComfyUI 可达、模型存在、输出可写） |
| `--start [--start-cmd ".."]` | 拉起 ComfyUI 并等待就绪（仅征得同意后使用） |
| `--config c --count N [--prompt/--names/--init/--denoise/--seed-basis/--host/--port]` | 跑图 |

## 配置字段（`config.example.json` / `--scaffold` 输出）
| 字段 | 说明 |
|---|---|
| `name` | 输出名 |
| `model` | 底模（`checkpoints/` 文件名） |
| `lora` / `lora_strength` | 可选 LoRA 与强度（图生图可省或调低） |
| `positive` / `negative` | 正面/负面 prompt |
| `width/height/steps/cfg/sampler/scheduler/denoise` | 采样参数 |
| `start_cmd` | 可选的 ComfyUI 启动命令（供 `--start` 使用） |
| `output_dir` / `prefix` | 保存目录与前缀 |
| `prompts` | 命名 prompt（`{name, prompt}` 或字符串） |

## 集成
- **DSH**：`SKILL.md`（frontmatter）可被 DSH/Anthropic 式 loader 加载。
- **其他 agent**：`AGENTS.md` 是通用指令入口；`pipeline.py` 可被任何能跑 Python 的 agent 调用。

## License
MIT（见 `LICENSE`）。本仓库仅为工具/文档，不含任何生成内容或第三方素材。
