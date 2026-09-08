# 本项目出图流程（用 DSH 控制 ComfyUI，一键完成扫描 + 配置 + prompt + 出图）

把用户"想画什么"变成图：先扫描可用模型/LoRA，问清模型与输出，生成配置，再批量出图。用户不碰 JSON、不手写复杂提示词。

## 环境（先探活）
- ComfyUI Desktop 版；端口常见 `http://127.0.0.1:8188`，重启后可能切 8189 → `GET /system_stats` 探活。
- 模型根 `G:\ComfyUI_Models`；底模在 `checkpoints\`，LoRA 在 `loras\`。
- 新增模型/LoRA 后列表看不到 → 重启 ComfyUI（本盘目录 mtime 不随新文件更新，缓存不刷新）。
- 输出 `C:\Users\19000\OneDrive\图片\<子文件夹>\`（SaveImage 前缀 `<子文件夹>/<name>`）。

## 工具
`auto-comfy-draw\`（`pipeline.py` + `config.example.json` + `README.md` + `SKILL.md`）。配置驱动、内容无关。

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

## 采样默认
832×1216（宽景 1344×768）、dpmpp_2m/karras、26~28 步、CFG 6.0~6.5、denoise 1.0。
