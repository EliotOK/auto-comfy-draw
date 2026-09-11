# auto-comfy-draw 项目约定

- 出图、配置与操作流程的唯一入口是 [SKILL.md](SKILL.md)，需要执行这些任务时读取。
- 修改驱动时共用 `pipeline_common.py` 的解析与校验。字段变化同步 `config.schema.json` 与 `docs/USAGE.md`。
- 修改后运行 `python -B -m unittest discover -s tests -v`，再用受影响脚本 `--dry-run` 验证建图；在线 `--check` 需要已运行的 ComfyUI。
- 用户配置、模型、原图、实验记录和现有输出属于用户数据。通用文档使用环境占位符，本机路径留在工作区级说明中。
