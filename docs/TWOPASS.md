# 精修、顺序输出与实验说明

`pipeline_twopass.py` 构建文生图 → 精修 → 可选放大的单次工作流。基础 CLI、输出字段和分支语义见 [USAGE.md](USAGE.md)。图生图使用 pipeline.py。

## 精修依赖

默认启用脸部与手部精修；需要 Impact Pack 相关节点及其配套检测节点安装可用。在线 check 会检查当前工作流用到的实际节点和模型枚举：

- 脸：UltralyticsDetectorProvider、FaceDetailer、SAMLoader；默认 bbox/face_yolov8m.pt 与 sam_vit_b_01ec64.pth。detail.face.sam=null 可不使用 SAM。
- 手：UltralyticsDetectorProvider、BboxDetectorSEGS、DetailerForEach；默认 bbox/hand_yolov8s.pt。
- 放大：UpscaleModelLoader、ImageUpscaleWithModel、ImageScale；默认 RealESRGAN_x4plus_anime_6B.pth，宽 2048，按原尺寸比例取整到 8 的倍数。

`--no-face` / `--no-hand` 关闭相应阶段；`--upscale` / `--no-upscale` 开关放大；`--upscale-width` 指定目标宽度；`--face-denoise` / `--hand-denoise` 覆盖重绘强度。配置 detail.face / hand / upscale 可设置更细参数，见 config.schema.json；缺省保留脚本默认。

`--seq` 仅在下载模式把下载件顺序命名为 `<seq-name>_NNN.png`。直写模式已在 SaveImage 前缀中分配系列序号。

## 对照与复现

`--seed-fixed --seed-basis N --count 1` 使各 prompt 使用同一随机种子，不保证更换提示词后构图、相机和背景不变。脸部种子为图像 seed+1，手部为 seed+2。需要比较结果时保存配置、最终展开提示词、种子、环境与图片，而非仅保留基准种子。

历史观测：同配置同种子在一次多任务连发中出现过约 23% 像素差异，单任务连续三次提交逐像素一致。该记录说明应实际核对精确复现，不足以证明差异原因。`--names` 挑选子集后，选中列表序号变化，后续派生种子也会变化。

## 本机历史兼容性记录

以下是特定环境的观测，使用前核实当前环境：

- G 盘曾出现 write/edit 的临时文件与硬链接操作报 EISDIR，可用直接 UTF-8 文件写入方式处理。
- 历史 PowerShell 5.1 不提供 utf8NoBOM 枚举；以实际运行版本为准。
- 基础脚本旧版本只在 scaffold 应用 prefix；当前运行也接受 --prefix。
- 分支标签曾将权重中的冒号带入文件名；twopass 现对分支文件名标签过滤非法字符。
