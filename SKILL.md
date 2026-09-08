---
name: auto-comfy-draw
description: Help a user configure a ComfyUI workflow and generate good prompts without writing them by hand, then batch-run text-to-image or image-to-image and deliver outputs. The user describes the desired image; this skill handles scanning available models/LoRAs, building a config, writing prompts, and running.
---

# ComfyUI 一键绘图助手（auto-comfy-draw）

帮用户把"想画什么"变成"做好的图"：**配工作流 + 写 prompt + 批量出图**，用户不碰 JSON、不手写复杂提示词。

## 第一次上手（onboarding，先做这些）
0. **ComfyUI 没起？先征求同意**
   - 若 `--discover`/`--check`/运行报 `ComfyUI not reachable` → **先提醒用户**"ComfyUI 还没启动"。
   - **征求同意**："要我帮你启动吗？还是允许我以后自动拉起（把启动命令存进配置）？"
   - 同意 → `python pipeline.py --start --start-cmd '<启动命令>'`（或读配置里已有的 `start_cmd`），等待就绪。
   - 不同意 / 自动启动失败 → **让用户自己启动**（Desktop 或 `python main.py`），再继续。
   - ⚠️ **绝不未经同意就拉起**；`--start` 只在你已获用户许可后使用。
1. **扫描可用资源**：`python pipeline.py --discover` → 列出 ComfyUI 当前能用的**底模**和 **LoRA**（这决定了用户能选什么）。
   - 若发现预期模型/LoRA 不在列表 → 提示用户**重启 ComfyUI**（新文件启动时才扫入）。
2. **问清这几个**（一次问完，别让用户写配置）：
   - 用哪个**底模**（从 `--discover` 结果里挑）？
   - 要不要 **LoRA**？哪个（可省）？
   - **输出到哪**（目录）？给个默认建议。
   - **尺寸 / 风格 / 是否垫图**？一句话描述想要什么？
3. **生成配置**：`python pipeline.py --scaffold --model <m> [--lora <l>] --output-dir <dir> --name <x> --config config.<x>.json`
   - 会写出含 `positive/negative/prompts` 的配置；`--prompts "a|b"` 可预填命名 prompt。
4. **自检**：`python pipeline.py --check --config config.<x>.json` → 确认模型存在、输出目录可写。
5. **跑图**：`python pipeline.py --config config.<x>.json --count N [--prompt "..."] [--names a,b] [--init ref.png --denoise 0.6] [--seed-basis N]`。

## 之后每次用
- 用户说一句要什么 → 用已有 config，`--prompt` 直接给描述（或 `--names` 挑命名 prompt），跑图。
- 垫图改图：`--init <basename>` + `--denoise`（先把参考图放进 ComfyUI `input` 目录）。
- 不满意：换 `--seed-basis` / 改 prompt / 增细节再跑。

## 关键能力
- **文生图/图生图**、**批量+轮询**（`/queue`、`/history/<pid>`）、**下载到 output_dir**、**失败/超时非零退出**、`POST /queue {"clear":true}` 取消。
- **远程**：`--host/--port` 指向本地或远程实例。
- **可复现**：`--seed-basis N`。

## 给 agent 的提示
- **别让用户写 prompt/配置**——你替他用 `--discover` 结果问清楚，再 `--scaffold` 生成，交给用户确认即可。
- 一句话不清，先澄清主体/风格/构图/是否垫图/输出位置，再动手。
- 交付给 `SAVED:` 路径，主动问是否换 seed / 加细节。

## 可移植性
`pipeline.py` 只需 Python + 可达的 ComfyUI HTTP API；`SKILL.md` 可被 DSH/Anthropic 式 loader 加载，`AGENTS.md` 供读该文件的 agent。
