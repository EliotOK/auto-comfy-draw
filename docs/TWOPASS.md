# pipeline_twopass.py 详解

> `pipeline_twopass.py` 是 `pipeline.py` 的超集；配置格式完全兼容。本文件收纳其操作细节与踩坑清单。

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

## 实测踩过的坑（血泪清单，别重复踩）

1. **`--prefix` 在 `pipeline.py` 里只对 `--scaffold` 生效，运行时被忽略**；`pipeline_twopass.py` 里才真正生效。输出目录由 `output_dir` + `prefix` 共同决定，`prefix` 带斜杠会**再建一层子目录**。
2. **种子按「在选中列表中的序号」算**（`basis + idx*100000`）。用 `--names` 只选一部分，后续 prompt 的种子会整体前移，**A/B 对照会失效**。
3. **`{|}` 里若含权重写法（如 `(wariza:1.3)`），文件名会带上非法字符 `:`** → SaveImage 报错。分支名已做 `[^A-Za-z0-9._-]` 过滤。
4. **同一配置同一种子未必复现**：实测出现过一次 23% 像素差异（多任务连发批次），但单任务连续三次提交逐像素一致。**`--seed-basis` 是记账约定，不是硬保证**；要精确复现就重跑核对。
5. **`write`/`edit` 工具在 G 盘上可能报 `EISDIR`**（该卷不支持其临时文件+硬链接落盘）。用 `[System.IO.File]::WriteAllText` 直写无 BOM UTF-8 规避。
6. **PowerShell 是 5.1**，没有 `utf8NoBOM` 枚举。
