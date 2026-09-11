# 提示词工程原则（本项目实测得出，优先于通用经验）

> 从 `AGENTS.md` 拆出；做 prompt 设计 / 对照实验时阅读。

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
