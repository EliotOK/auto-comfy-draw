---
name: auto-comfy-draw
description: Help a user configure a ComfyUI workflow and generate good prompts without writing them by hand, then batch-run text-to-image or image-to-image and deliver outputs. The user describes the desired image; this skill handles scanning available models/LoRAs, building a config, writing prompts, and running.
---

# ComfyUI 一键绘图助手（auto-comfy-draw）

帮用户把"想画什么"变成"做好的图"：**配工作流 + 写 prompt + 批量出图**，用户不碰 JSON、不手写复杂提示词。

## 用户怎么开口（推荐 prompt）→ agent 怎么接
用户**只对话，不打 CLI**。`--discover` / `--scaffold` 等命令是**你（agent）在底层执行的**，把用户的话翻译成动作：

| 用户开口 | 你该做的 |
|---|---|
| "帮我画一张 <描述>"（首次） | `--discover` 列可用模型 → 问模型/LoRA/输出/尺寸/是否垫图 → `--scaffold` 生成配置 → `--check` → 跑图 |
| "用 <模型> <lora> 画 <描述>"（已给信息） | 直接 `--scaffold` 或复用已有 config，`--prompt` 跑图 |
| "把这张/垫图改成 <风格>"（img2img） | `--init <参考图文件名> --denoise N` 跑图 |
| "换个种子 / 再来 N 张 / 加点细节" | 改 `--seed-basis` / `--count` / 改 prompt 重跑 |
| "别让我写 prompt；我不知道怎么写" | 你代他组织 prompt（按 config `positive`/`negative` 结构） |
| "输出到 <目录> / 用某个模型" | 更新 config（`--scaffold` 或改 `output_dir`/`model`）再跑 |

**推荐开场白（用户可说）**：
- "帮我画一张傍晚的城市天际线"
- "用 waiIllustriousSDXL 和 xxx LoRA 画一只猫在屋顶，输出到 D:/my_imgs，出 4 张"
- "把这张 ref.png 改得更写实一点"

你收到后**一步步走 onboarding**，而不是叫用户去敲命令行。

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

## 输入参数（描述范式 · 供 agent 填写）

**填写规则（先读）**
- **只有 agent 填参数，用户只说话**。能从 `--discover`/环境推断的（模型名、端口）**不要问用户**。
- **必填缺失就追问**（`--model`、`--output-dir`）；**可选项一律取默认，不要问**。
- **枚举只能用 `--discover` 列出的值**（模型/LoRA 文件名须完全一致）。
- **互斥**：`--prompt` 与 `--names` 二选一；`--server-out`（直写、不下载）与本地 `output_dir` 下载模式二选一。
- **格式**：路径原样传；`--width/--height` 取 8 的倍数；prompt 用 danbooru 标签风格（Illustrious 系）；多 prompt 用 `|` 分隔。
- 改完脚本先 `--dry-run` 干跑验证（`pipeline_twopass.py`）。

### 模式开关（互斥，选一个）
| 参数 | 类型 | 说明 |
|---|---|---|
| `--discover` | flag | 列出 ComfyUI 可用底模/LoRA（首次 onboarding） |
| `--scaffold` | flag | 生成配置 JSON（需 `--model`、`--output-dir`） |
| `--check` | flag | 自检（可达 / 模型存在 / 输出可写） |
| `--start` | flag | 拉起 ComfyUI 并等待就绪（**须先经用户同意**；用 `--start-cmd` 或配置 `start_cmd`） |
| （默认） | — | 出图，需 `--config` |

### A. 配置参数（配 `--scaffold` 用）
| 参数 | 类型 | 必填 | 默认 | 含义 / 何时用 |
|---|---|---|---|---|
| `--model` | str | ✅ | — | 底模文件名，取值必须来自 `--discover` |
| `--lora` | str | ✖ | null | 角色/风格 LoRA，可省 |
| `--lora-strength` | float | ✖ | 0.9 | LoRA 强度；参考图流程可降到 0.4–0.6 |
| `--name` | str | ✖ | demo | 输出名（直写模式下也作默认子目录名） |
| `--output-dir` | str | ✅ | — | 下载模式保存目录；直写模式可忽略 |
| `--width` / `--height` | int | ✖ | 832 / 1216 | 尺寸（宽景 1344×768），8 的倍数 |
| `--steps` / `--cfg` | int / float | ✖ | 28 / 6.5 | 采样步数 / CFG |
| `--sampler` / `--scheduler` | str | ✖ | dpmpp_2m / karras | 采样器 / 调度器 |
| `--positive` / `--negative` | str | ✖ | 内置 | 正 / 负 prompt 基础 |
| `--prompts` | str | ✖ | 空 | `a|b` 预填命名 prompt |
| `--start-cmd` | str | ✖ | 空 | ComfyUI 启动命令（供 `--start`） |
| `--config` | str | ✅ | — | 写出的配置路径 |

### B. 出图参数（`--config` 模式）
| 参数 | 类型 | 默认 | 含义 / 何时用 |
|---|---|---|---|
| `--config` | str | 必填 | 配置 JSON |
| `--count` | int | 3 | 每个 prompt 出几张 |
| `--prompt` | str | null | 临时 prompt（`|` 分隔多个） |
| `--names` | str | null | 只跑 config 里的命名 prompt（逗号分隔）；与 `--prompt` 互斥 |
| `--init` | str | null | 参考图文件名（须在 ComfyUI `input` 目录）→ img2img |
| `--denoise` | float | 1.0 | img2img 重绘强度（配 `--init`，常用 0.4–0.7） |
| `--seed-basis` | int | 随机 | 复现基准：种子 = `basis + 序号*100000 + k` |
| `--server-out` | str | null | **服务端输出根** → 直写模式：只读目录拿序号、跳过下载（不写工作区外） |
| `--server-sub` | str | config.name | 直写模式的子目录 |
| `--host` / `--port` | str / int | 127.0.0.1 / 探 8188,8189 | 远程实例 |

### C. `pipeline_twopass.py` 追加参数（详见 `AGENTS.md`）
| 参数 | 说明 |
|---|---|
| `--pick random\|cycle` | `{a\|b\|c}` 分支抽选（`cycle` = 每个分支都出现） |
| `--seed-fixed` | 所有 prompt 共用同一 seed（锁定布局；做对照必须加） |
| `--no-face` / `--no-hand` | 关闭面部 / 手部精修 |
| `--upscale` / `--upscale-width N` | RealESRGAN 放大 |
| `--face-denoise` / `--hand-denoise` | 精修重绘强度 |
| `--seq` | 非直写模式把下载件重命名为 `<name>_NNN.png` |
| `--dry-run` | 只打印不提交 |

### 机器可读契约
配置字段的约束见 `config.schema.json`（JSON Schema）；agent 可用它校验 / 补全配置。

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
