# 本项目出图流程（用 DSH 控制 ComfyUI，一键完成扫描 + 配置 + prompt + 出图）

把用户"想画什么"变成图：先扫描可用模型/LoRA，问清模型与输出，生成配置，再批量出图。用户不碰 JSON、不手写复杂提示词。

## 环境（先探活）
- ComfyUI Desktop 版；端口常见 `http://127.0.0.1:8188`，重启后可能切 8189 → `GET /system_stats` 探活。
- 模型根 `<WORKSPACE>`；底模在 `checkpoints\`，LoRA 在 `loras\`。
- 新增模型/LoRA 后列表看不到 → 重启 ComfyUI（本盘目录 mtime 不随新文件更新，缓存不刷新）。
- 输出 `<COMFY_OUTPUT_ROOT>\<子文件夹>\`（SaveImage 前缀 `<子文件夹>/<name>`）。

## 工具
`auto-comfy-draw\`（`pipeline.py` + `pipeline_twopass.py` + `config.example.json` + `README.md` + `SKILL.md`）。配置驱动、内容无关。
`pipeline_twopass.py` 是 `pipeline.py` 的**超集**：多出「细节精修 / `{|}` 随机抽选 / 直写服务端输出 / 顺序命名」。配置格式完全兼容，见下节。

## 上手流程
0. **ComfyUI 没起？先征求同意**：若 `--discover`/`--check`/运行报 `not reachable` → 先提醒用户；**征得同意后再** `--start --start-cmd '<启动命令>'`（或读配置 `start_cmd`）拉起并等待就绪；不同意/失败就让用户自己启动再继续。**绝不未经同意就拉起。**
1. **扫描**：`python auto-comfy-draw\pipeline.py --discover` → 列出可用底模/LoRA。
2. **问清**：用哪个底模？要不要 LoRA？输出到哪？想要什么画面（尺寸/风格/是否垫图）？
3. **生成配置**：`python auto-comfy-draw\pipeline.py --scaffold --model <m> [--lora <l>] --output-dir <dir> --name <x> --config config.<x>.json`
4. **自检**：`python auto-comfy-draw\pipeline.py --check --config config.<x>.json`
5. **跑图**：`python auto-comfy-draw\pipeline.py --config config.<x>.json --count N [--prompt "..."] [--names a,b] [--init ref.png --denoise 0.6] [--seed-basis N] [--host/--port]`
   - 批量入队 + 轮询 `/queue`、`/history/<pid>`，下载到 output_dir，失败/超时非零退出；取消 `POST /queue {"clear":true}`。
6. **交付**：给 `SAVED:` 路径；按需换 seed / 构图 / 细节再跑。

> **用户只对话，不打 CLI**：`--discover`/`--scaffold`/`--check`/`--start`/`--config` 都是**你在底层执行的**。把用户的话翻译成命令（参考 SKILL.md 的"用户怎么开口→agent 怎么接"表），**绝不要让用户自己敲这些命令**；用户只需说"帮我画一张…"。

## 图生图 / 复现 / 远程
- **图生图**：`--init <basename>` + `--denoise N`（参考图放进 ComfyUI input 目录）。
- **复现**：`--seed-basis N` → 每 prompt 种子 = `N + 序号*100000 + 张数序号`。
- **远程**：`--host/--port`。

## 直写服务端输出 + 顺序命名（`pipeline_twopass.py`）

**背景（务必先懂这条）**：ComfyUI 服务端是独立进程、**不受 DSH 沙箱约束**，而它的输出目录默认就是 `<COMFY_OUTPUT_ROOT>`。DSH 的沙箱**只允许写工作区 `<WORKSPACE>`**——所以：

- ✅ **让服务端写它自己的输出目录**：正常、无需提权、一直是这么工作的。
- ❌ **让脚本自己写工作区外的目录**（把配置 `output_dir` 指向工作区外）：会被沙箱拒绝。**不要这么做**，也不要用 `danger-full-access` 去绕过。

**正确调用**（输出到工作区外的输出根一律走这条）：

```
python auto-comfy-draw\pipeline_twopass.py --config <cfg> --count N \
    --server-out "<COMFY_OUTPUT_ROOT>" --server-sub sparkle \
    [--pick cycle] [--no-face --no-hand]
```

- **`--server-out <服务端输出根>`**：开启**直写模式**。脚本只**读取**该目录以确定下一个序号，**跳过本地下载**，把 `filename_prefix` 下发给服务端由其落盘。全程不写 C 盘。
- **`--server-sub <子目录>`**（默认 `sparkle`）：`--server-out` 下的子目录；决定文件落在哪个文件夹。
- **落盘名**：`<子目录>/sparkle_NNN` + 服务端自动补的计数器 → 如 `sparkle_049_00001_.png`。**序号由脚本控制，计数器是服务端强制的、去不掉，排序正确即可，不要为此重命名文件。**
- **`--seq`**：仅在**非直写**（输出到工作区内）时用，把下载件重命名为 `sparkle_NNN.png`；对直写模式无效（无写权限）。

### `{|}` 随机抽选

**ComfyUI 核心确实原生支持 `{a|b|c}`**（`CLIPTextEncode.text` 带 `dynamicPrompts: True`），但**由前端在入队序列化时展开**（`Comfy.DynamicPrompts` 扩展改 `serializeValue`）。走 HTTP `/prompt` 直连**绕过前端**，所以脚本必须自己展开——`pipeline_twopass.py` 已实现。

- 语法：`{a|b|c}` 逐组展开，**不支持嵌套**；无花括号的文本原样通过。
- `--pick random`（默认）：用 `random.Random(seed)` 抽 → **同种子同分支，可复现**。
- `--pick cycle`：按序号轮转 → **一批内保证每个分支都出现**（要覆盖均匀就用它；忘了加就会走随机，可能漏掉分支）。
- 展开出的分支会写进日志的文件名栏（`[分支 -> sparkle_NNN#k/N]`），便于追溯。

### 其他开关

| 开关 | 作用 |
|---|---|
| `--no-face` / `--no-hand` | 关闭 Impact Pack 的脸部/手部精修（默认开启） |
| `--upscale` / `--upscale-width N` | RealESRGAN 动漫向放大 |
| `--face-denoise N` / `--hand-denoise N` | 精修重绘强度 |
| `--seed-fixed` | **所有 prompt 共用同一个种子**，锁定布局/相机/背景，使「唯一变量是 prompt」。做**控制对照**（表情递进、单变量测试）必须加 |
| `--dry-run` | 只打印图，不提交（**改完脚本先干跑验证**） |

**`--seed-fixed` 为什么必要**：不加时每个 prompt 用 `basis + idx*100000`，**六个阶段就是六个完全不同的种子，构图与背景整张重掷**（实测：同一批里出现了瓷砖地、木地板、暗窗景三种背景）。那样只能算灵感集，**不是**可比的对照序列。配 `--count 1` 才是纯净扫描；`--count N` 时每个 prompt 内部仍会 `+k` 变种子。

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

## 实测踩过的坑（血泪清单，别重复踩）

1. **`--prefix` 在 `pipeline.py` 里只对 `--scaffold` 生效，运行时被忽略**；`pipeline_twopass.py` 里才真正生效。输出目录由 `output_dir` + `prefix` 共同决定，`prefix` 带斜杠会**再建一层子目录**。
2. **种子按「在选中列表中的序号」算**（`basis + idx*100000`）。用 `--names` 只选一部分，后续 prompt 的种子会整体前移，**A/B 对照会失效**。
3. **`{|}` 里若含权重写法（如 `(wariza:1.3)`），文件名会带上非法字符 `:`** → SaveImage 报错。分支名已做 `[^A-Za-z0-9._-]` 过滤。
4. **同一配置同一种子未必复现**：实测出现过一次 23% 像素差异（多任务连发批次），但单任务连续三次提交逐像素一致。**`--seed-basis` 是记账约定，不是硬保证**；要精确复现就重跑核对。
5. **`write`/`edit` 工具在 G 盘上可能报 `EISDIR`**（该卷不支持其临时文件+硬链接落盘）。用 `[System.IO.File]::WriteAllText` 直写无 BOM UTF-8 规避。
6. **PowerShell 是 5.1**，没有 `utf8NoBOM` 枚举。

## 提示词工程原则（本项目实测得出，优先于通用经验）

### 1. 冲突打包：互斥属性塞进**同一个** `{|}` 选项，绝不做成交叉轴

反面教材：全局写 `arms up`，再用分支写 `on all fours` —— 四肢着地要求手掌撑地，不可能同时举手，模型只能二选一，画面含糊。
正确做法：`{wariza, 手臂上举…|on all fours, 手绑背后…}`，每个选项**内部自洽**。

同类陷阱：`solo` 与 `1boy` 直接互斥 → **不要把 `solo` 写进共享基础块**，改由每条 prompt 自己声明单人（`solo`）或伴侣（`1boy, faceless male, hetero`）。

### 2. 遮挡物必须与「它兼容的表情词」打包

| 遮挡物 | 封掉的通道 | 因此**不能**写 |
|---|---|---|
| `blindfold` | 眼 | `looking at viewer`、`looking away`、`averted gaze`、`half-closed eyes`、`teary eyes`、`closed eyes` |
| `ball gag` | 嘴 | `closed mouth`、`smile`、`grin`、`parted lips`、`tongue out`、`kiss`、`licking lips` |
| 两者叠加 | 眼 + 嘴都没了 | 只剩**眉、腮红、泪、口水、汗、颤抖、身体语言** |

**写 blindfold 时一个视线词都别写，写 gag 时一个嘴形词都别写。** 实测因此画面干净、无冲突残渣。（反面状态：蒙着眼还 `looking at viewer`、塞着口球还 `smile`。）

### 3. 以**物件**命名的行为，必须补「施动部位锚点」

- **自带施动部位、一次就成**：`kiss`／`neck kiss`（两张脸）、`breast fondling`（一只手）、`fingering`（手指）—— 标签逼着模型把伴侣画出来。
- **核心落在物件上、会崩**：`fellatio` 的核心是 `penis` → 模型渲染出一根**悬空器官**就"交差"，男性躯干丢失。

修法（实测全部有效）：
1. 补 `standing, male body, legs` —— 给躯干一个存在理由
2. 补 `from side` —— **强制双人同框，最有效的一条**
3. 补 `hand on another's head` —— 一个施动的手部标签，把两根身体连起来
4. 或改用 `pov` —— 从根上取消「需要男性身体」这个前提（沉浸感最强，代价是她身体被裁掉）
5. `faceless male` 是让男性只出手/躯干、不出脸的标准技巧，可降低**角色身份污染**

**通用判据：先问这个标签里有没有天然的施动部位；没有就补一个。**

### 4. 先入为主的标签会赢——服装轴要「裁剪」，不要「追加反向词」

角色基础块里的完整服装清单排在 `positive` 最前面，会把着装钉死：

- `disheveled clothes`／`torn clothes`／`damaged clothing` → **完全无效**（要求模型"破坏"一件训练权重极强的服装）
- `clothing aside`／`breasts out`／`one breast out`／`panties`／`upskirt` → **有效**（只"改变某块布的搭法"或露出本就存在的衣物）

**结论：要服装变化就按阶段裁剪基础块；想做的是「解除」而不是「破坏」。** 下摆短的服装可以直接出 `panties` 要素，不必衣不蔽体。

### 5. 器械与装置是**种子依赖**的，靠数量挑

`wooden horse`／`shibari`／`pillory`／`suspension`／`blindfold`／`ball gag` 在这类角色 LoRA 里训练频次≈0，全靠底模。实测**同一提示词**：一个种子只在画面底缘露出一小块木方，另一个种子给出完整四腿锯木架。

**对策：多出几张挑，比反复调词有效。** 可辅以 `sawhorse, wooden trestle` 或加权重提高识别度。

### 6.「未训练」≠「画不出」，但 = 「不可控」

底模对 Danbooru 常用标签很熟，表情、裸露、装置都画得出来；但 **LoRA 训练里没有的标签，细节不可控、角色身份保真度会掉**，双人构图时尤其明显。

**判断依据**：直接读 LoRA 的 `ss_tag_frequency`——`safetensors` 头部 8 字节是 JSON 头长度，`__metadata__` 里含 `ss_tag_frequency`（各数据集逐标签频次）与 `modelspec.tags`（作者声明的触发词）。先查频次，再决定是"用它"还是"靠数量挑"。

典型量级参考（2374 张角色 LoRA）：`smile` 829、`blush` 451、`completely nude` 259、`armpits` 74、`finger to mouth` 60、`nipples` 32、`1boy` 11、`shibari` 3、`blindfold` 0、`fellatio` 0。

### 7. 一次只改一个变量

换分辨率／换种子会**重掷构图**，不是纯对照；要锁定布局用 `--seed-fixed`。诊断顺序：先看图 → 定位是标签冲突、训练覆盖、还是装置不稳定 → 只改那一项再跑。

## 采样默认
832×1216（宽景 1344×768）、dpmpp_2m/karras、26~28 步、CFG 6.0~6.5、denoise 1.0。
