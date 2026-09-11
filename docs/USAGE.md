# 运行参考

Python 3.7+，仅使用标准库。脚本路径相对于本 skill 目录，配置路径相对于调用时的工作目录。

## 能力与入口

| 能力 | pipeline.py | pipeline_twopass.py |
|---|---|---|
| discover / scaffold / start | 支持 | 使用基础脚本 |
| check / dry-run | 支持 | 支持 |
| 文生图 / LoRA / 分支抽选 / 固定种子 | 支持 | 支持 |
| 图生图 init / denoise | 支持 | 不支持 |
| 脸手精修 / 模型放大 / seq 重命名 | 不支持 | 支持 |
| 服务端直写 | 支持 | 支持；编号需客户端可读服务端输出根 |

`--discover`、`--scaffold`、`--start`、`--check`、`--dry-run` 为互斥模式；不指定模式即出图。twopass 的附加能力和依赖见 [TWOPASS.md](TWOPASS.md)。

## 示例

以下命令由 agent 执行，路径应替换成实际环境：

```text
python pipeline.py --discover
python pipeline.py --scaffold --model model.safetensors --output-dir ./output --name city --config config.city.json
python pipeline.py --config config.city.json --prompt "a {red|blue} bird" --count 2 --pick cycle --dry-run
python pipeline.py --config config.city.json --check
python pipeline.py --config config.city.json --count 2 --seed-basis 100
python pipeline.py --config config.city.json --init ref.png --denoise 0.6 --count 1
```

首次安装的可复制 prompt 与连接引导见 [README](../README.md#安装复制这段话给-agent)。discover 没有发现底模时会警告生成需要兼容底模；没有 LoRA 时提示其为可选项。

scaffold 离线生成配置，资源存在性由 discover / check 验证。scaffold 需 `--model` 和 `--output-dir` 或 `--server-out`；`--config` 省略时写 `config.<name>.json`。默认 name 为 demo，尺寸 832×1216，steps 28，cfg 6.5，sampler dpmpp_2m，scheduler karras，denoise 1.0。可指定 `--lora`、`--lora-strength`、`--positive`、`--negative`、`--prefix`、`--prompts`、`--start-cmd`。生成配置会覆盖指定配置文件，复用前先检查已有内容。

## 运行参数

- `--config` 必填；运行参数从配置读取。`--prefix` 可在运行时覆盖输出前缀。
- `--count` 为每条 prompt 的张数，必须大于零。基础脚本默认 3，twopass 默认 1；agent 应按用户要求显式指定。
- `--prompt` 临时替换配置 prompts，仍拼接配置 positive；`--names a,b` 挑选命名项。二者互斥，任一未知名称报错。选择按配置原有顺序执行。
- `--seed-basis N`：种子为 `N + 选中prompt序号*100000 + 张序号`，序号从 0 开始。省略时生成并打印一次 SEED_BASIS。
- `--seed-fixed`：所有 prompt 共用基准种子，无需同时指定 seed-basis；各自第 k 张仍加 k。对照通常显式指定 basis 并设 count=1。
- `--host` 默认 127.0.0.1；省略 `--port` 探测 8188、8189。HTTP 连接需目标服务可达。
- `--timeout` 为入队完成后的批次等待时限（秒），基础脚本默认 2400，twopass 默认 3600。请求超时与轮询可能使总耗时略超此值；超时不自动取消已提交任务。
- 基础脚本的 `--init` 读取服务端 input 中的图片。图生图按参考图实际尺寸编码；配置 width/height 仅用于文生图，不会缩放参考图。

## 提示词分隔和覆盖

顶层 `|` 分隔不同 prompt；`{a|b|c}` 在单条 prompt 内抽选，支持多个组，不支持嵌套；不平衡花括号报错。空的顶层项被忽略，完全空的 CLI prompt 报错。配置 prompts 为空时只使用一次 positive。

- `--pick random` 默认按图像种子确定分支。
- `--pick cycle` 按任务序号让每组同步轮转。对同一条 prompt，count 至少等于最大组长度才覆盖各组选项；不会枚举笛卡尔积。组合全覆盖时在 config.prompts 显式列出所需组合。

## 输出

配置 `server_output_dir` 是规范字段，`server_out` 字符串为旧别名；命令行 `--server-out` 优先。两种配置路径同时存在但不同且没有 CLI 覆盖时拒绝运行。旧 scaffold 的布尔标记会归一化；true 必须同时有明确服务端路径。旧 denoise=null 按原设计默认值 1.0 解释。

有服务端输出根时跳过客户端下载，output_dir 可省略；否则 output_dir 必填。可同时保留 output_dir 作为下载模式配置，但直写时不使用它。此参数不会更改 ComfyUI 的实际输出根，必须填写服务端真实设置。

`--server-sub` 默认配置 server_sub，再回退 config.name（缺失时 pipeline）。twopass 的 `--seq-name` 默认 config.name；旧调用若依赖 sparkle 前缀，应显式传 `--seq-name sparkle --server-sub sparkle`。服务端继续追加自己的计数器，不为去掉该计数器重命名。

基础脚本可在客户端无法访问服务端目录时报告路径；twopass 顺序编号要求根目录可读，根目录下尚未存在的系列从 1 开始，由服务端创建。并发运行可能选择同一系列序号；需要严格连续编号时串行执行。

## 校验与交付

两份驱动运行前均从 config.schema.json 校验配置。内部校验器只实现该文件所用的 Schema 子集，不自动注入 Schema default；工作流构建负责默认值。未知扩展字段保留，但不会自动产生功能。

`--dry-run` 离线打印全部 jobs 和 graphs，不连接服务、不创建目录、不提交任务。直写模式仍可能读取输出目录以规划编号。

`--check` 使用所选驱动与当前运行参数建图，通过 `/object_info` 检查所用节点、必填输入、枚举资源和数值范围。预检会汇总并去重可检测的缺失节点、不可用枚举资源、缺失必填项和数值范围错误，附带处理建议；任一问题都会阻止整个批次入队。节点缺失时无法检查它的资源列表，补齐后需要重跑。

下载目录用临时文件验证写入后自动清理；直写不试写服务端目录。实际出图同样自动预检。检查不验证模型架构相容性、显存容量、插件自定义校验和最终图像质量。

批次逐项入队并轮询 `/history/<prompt_id>`；保留 queued 日志中的任务 ID。服务端失败、输出缺失、下载失败或超时以非零状态结束。发生中途提交失败时已入队任务仍可能继续，先查明状态再决定是否补交；不要直接重提整个批次。

取消排队任务时只提交已确认属于本批次的 ID：`POST /queue {"delete": ["<prompt_id>"]}`。运行中任务不由该操作停止；先确认队列归属和服务端中断能力，勿清空其他任务。
