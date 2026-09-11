# 本项目出图流程（用 DSH 控制 ComfyUI，一键完成扫描 + 配置 + prompt + 出图）

把用户"想画什么"变成图：先扫描可用模型/LoRA，问清模型与输出，生成配置，再批量出图。用户不碰 JSON、不手写复杂提示词。

## 关键规则（先读）
- **用户只对话，不打 CLI**：`--discover`/`--scaffold`/`--check`/`--start`/`--config` 都是你在底层执行；把用户的话翻译成命令（映射表见 `SKILL.md`）。**绝不让用户自己敲命令。**
- **输入参数只有 agent 填**：能从 `--discover`/环境推断的**不要问**；必填缺失（`--model`、`--output-dir`）才追问；枚举只取 `--discover` 输出。参数总表见 `SKILL.md`，机器可读契约 `config.schema.json`。
- **ComfyUI 未启动**：先提醒 → **征得同意后**才 `--start`（`--start-cmd` 或配置 `start_cmd`）；不同意/失败就让用户自己启动。**绝不未授权拉起。**
- **要输出到工作区外**（如服务端输出根）：走 `--server-out <根> --server-sub <子目录>` **直写模式**（脚本只读序号、跳过下载）；**不要**让脚本自己写工作区外，也**不要**用 `danger-full-access` 绕过。详见 `docs/TWOPASS.md`。
- **改完脚本先 `--dry-run` 干跑**；**一次只改一个变量**。

## 详细文档（按需阅读）
| 文档 | 内容 |
|---|---|
| `SKILL.md` | 用户开口 → agent 动作映射；**完整参数表** |
| `README.md` / `README.en.md` | 面向使用者的说明（中文 / English） |
| `docs/TWOPASS.md` | `pipeline_twopass.py`：细节精修 / `{\|}` 抽选 / 直写模式 / 顺序命名 / **踩坑清单** |
| `docs/PROMPT_ENGINEERING.md` | **7 条提示词工程原则**（本项目实测） |
| `config.schema.json` | 配置的机器可读契约（JSON Schema） |

## 环境（先探活）
- ComfyUI Desktop 版；端口常见 `http://127.0.0.1:8188`，重启后可能切 8189 → `GET /system_stats` 探活。
- 模型根 `<WORKSPACE>`；底模在 `checkpoints\`，LoRA 在 `loras\`。
- 新增模型/LoRA 后列表看不到 → 重启 ComfyUI（本盘目录 mtime 不随新文件更新，缓存不刷新）。
- 输出 `<COMFY_OUTPUT_ROOT>\<子文件夹>\`（SaveImage 前缀 `<子文件夹>/<name>`）。

## 工具
`auto-comfy-draw\`（`pipeline.py` + `pipeline_twopass.py` + `config.example.json` + `README.md` + `SKILL.md`）。配置驱动、内容无关。
`pipeline_twopass.py` 是 `pipeline.py` 的**超集**：多出「细节精修 / `{|}` 随机抽选 / 直写服务端输出 / 顺序命名」。配置格式完全兼容；细节见 `docs/TWOPASS.md`。

## 上手流程
0. **ComfyUI 没起？先征求同意**：若 `--discover`/`--check`/运行报 `not reachable` → 先提醒用户；**征得同意后再** `--start --start-cmd '<启动命令>'`（或读配置 `start_cmd`）拉起并等待就绪；不同意/失败就让用户自己启动再继续。**绝不未经同意就拉起。**
1. **扫描**：`python auto-comfy-draw\pipeline.py --discover` → 列出可用底模/LoRA。
2. **问清**：用哪个底模？要不要 LoRA？输出到哪？想要什么画面（尺寸/风格/是否垫图）？
3. **生成配置**：`python auto-comfy-draw\pipeline.py --scaffold --model <m> [--lora <l>] --output-dir <dir> --name <x> --config config.<x>.json`
4. **自检**：`python auto-comfy-draw\pipeline.py --check --config config.<x>.json`
5. **跑图**：`python auto-comfy-draw\pipeline.py --config config.<x>.json --count N [--prompt "..."] [--names a,b] [--init ref.png --denoise 0.6] [--seed-basis N] [--host/--port]`
   - 批量入队 + 轮询 `/queue`、`/history/<pid>`，下载到 output_dir，失败/超时非零退出；取消 `POST /queue {"clear":true}`。
6. **交付**：给 `SAVED:` 路径；按需换 seed / 构图 / 细节再跑。

## 图生图 / 复现 / 远程
- **图生图**：`--init <basename>` + `--denoise N`（参考图放进 ComfyUI input 目录）。
- **复现**：`--seed-basis N` → 每 prompt 种子 = `N + 序号*100000 + 张数序号`。
- **远程**：`--host/--port`。

## 输入参数（描述范式 · 摘要；完整表见 `SKILL.md`）

**填写规则**
- **只有 agent 填参数，用户只说话**；能从 `--discover`/环境推断的（模型名、端口）**不要问**；必填缺失（`--model`、`--output-dir`）才追问；可选项取默认。
- **枚举只能取 `--discover` 的输出**（模型/LoRA 名须完全一致）。
- **互斥**：`--prompt` ↔ `--names`；`--server-out`（直写、不下载）↔ 本地 `output_dir` 下载模式。
- **格式**：路径原样；`--width/--height` 取 8 的倍数；多 prompt 用 `|`；prompt 用 danbooru 标签风格。

**模式**：`--discover` ｜ `--scaffold` ｜ `--check` ｜ `--start`（**须先经用户同意**）｜ 默认（需 `--config`）。

| 组 | 参数（类型/默认） |
|---|---|
| 配置 | `--model`(str,必填·来自discover)、`--lora`(str,null)、`--lora-strength`(0.9)、`--name`(demo)、`--output-dir`(str,必填)、`--width/--height`(832/1216)、`--steps/--cfg`(28/6.5)、`--sampler/--scheduler`(dpmpp_2m/karras)、`--positive/--negative`、`--prompts`("a\|b")、`--start-cmd`、`--config`(必填) |
| 出图 | `--config`、`--count`(3)、`--prompt`、`--names`、`--init`、`--denoise`(1.0)、`--seed-basis`、`--server-out`(服务端输出根)、`--server-sub`、`--host/--port` |
| twopass 追加 | `--pick random\|cycle`、`--seed-fixed`、`--no-face/--no-hand`、`--upscale/--upscale-width`、`--face-denoise/--hand-denoise`、`--seq`、`--dry-run` |

**机器可读契约**：`config.schema.json`（JSON Schema），可用它校验/补全配置。

## 采样默认
832×1216（宽景 1344×768）、dpmpp_2m/karras、26~28 步、CFG 6.0~6.5、denoise 1.0。
