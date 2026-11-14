# brickbot 0.2.1

LDraw 积木装配核心（非 LEGO 官方项目）

Python、JSON CLI、Skill 与真实 DSH 插件共用 `brick_engine.Engine`。

官方 LDraw 快照筛选 **109 件**：Brick 38、Plate 34、Tile 21、Baseplate 16。**94 件完整验证、15 件 unknown、0 件解析失败**；106 件有已提取接口，共 **13,327 个接口**。按类别、尺寸正则和矩形模具后缀筛选，新增 14 件多层高砖，包含 1×1×3、1×2×2、1×2×3、1×2×5、2×2×3、1×4×3、1×6×5；不维护零件编号白名单。覆盖与逐件原因见 `evidence/coverage.json`。

参考取水工具 **65 件、9 个分组步骤**，几何验收 pass。内腔 **96×96×70.4 mm**，扣除底板凸点排水体积后 **644.637 mL**。LDraw 官方 71 浅灰、15 白色墙层与 72 深灰夹层，19 Tan 握持耳；相对两面中部各一块 4×8 握持耳，两排凸点夹在上下墙层之间，各有 16 个下接收连接和 16 个上凸点连接，外伸 16 mm，不侵入内腔。墙体转角逐层换向咬合。承载、夹持力、材料变形与实际防水仍 unknown，容量沿用用户指定的无缝不漏水假设。

## 安装

```sh
uvx git+https://github.com/YifanLiu-AI/brickbot --help                         # 免安装试用
uv tool install git+https://github.com/YifanLiu-AI/brickbot                    # 安装 brickbot 命令
echo '{"op":"describe","part":"3001"}' | brickbot
npx jsr add @shiyi/brickbot                                                     # DSH 插件
```

插件未设置 `BRICK_ENGINE_PYTHON` 时自动用 `uvx` 调用本仓库 v0.2.1；需先装 [uv](https://docs.astral.sh/uv/)。旧命令名 `brick-engine` 仍可用。Release 附 wheel / sdist。包内含 catalog、真实网格、递归所需 LDraw 源文件和许可证。

## 网格接口

每个接口含 `grid:[column,row]`，两项均为整数，从 0 开始。原点是该零件局部外框 **最小 X、最小 Z 方向的凸点中心**；列向 +X，行向 +Z，间距 20 LDU（8 mm）。LDraw +Y 向下，1 LDU=0.4 mm。坐标在旋转前的局部坐标系内；新件旋转不会改变其 `anchor` 编号。`grid.column_range`、`row_range` 给出闭区间；名称尺寸的顺序未必等于局部 X/Z，按 describe 的范围选。

`add/propose` 首选 `target_stud:[c,r]`（已有件）和 `anchor:[c,r]`（新件）。旧的 `target_interface:"sN"`、`interface:"aN"` 保留；同时传入网格和序号时必须指向同一接口。网格范围内若接口没有通过几何验证，也返回 `E_INTERFACE`。

**序号不能当坐标。** s* 按原语遍历排序，a* 按底部空腔遍历排序。3001 的 `s0→a0` 会错位叠放：实测沿 +X 三格、沿 +Z 一格；同型号零旋转齐边叠放应使用相同网格，例如 `[0,0]→[0,0]`。不同尺寸件使用相同网格表示对齐局部最小 X/Z 的凸点，不是对齐零件中心。

`describe` 接受 `compact:true/false`。省略时，接口超过 64 个自动精简；16×16 板默认只返回标识、尺寸、网格范围、接口类型计数、验证状态和规则。`compact:false` 才展开全部接口、几何和来源；`Engine.part()` 供程序读取完整数据。

## CLI 与 Python

标准输入一个 JSON 对象，或使用 `--input request.json`。每次标准输出一个 JSON 对象。add 失败不修改 assembly；成功后保存返回的 assembly 再传入下一次。完整 CLI 示例见 `SKILL.md`。

| op | 参数 |
|---|---|
| search | query、limit |
| describe | part、compact（可省略） |
| root | part、id、color |
| propose / add | assembly、part、target、target_stud、anchor、rotation、id、structure、color；或旧接口序号 |
| validate / order | assembly |
| export | assembly、directory |

```python
from brick_engine import Engine
engine = Engine()
assembly = engine.root('91405', id='base')
engine.add(assembly, part='3001', target='base', target_stud=[2,2],
           anchor=[0,0], rotation=0, id='wall', color=7)
assert engine.validate(assembly)['status'] == 'pass'
engine.export(assembly, 'output')
```

`propose` 只解位姿，不作装配验收；`add` 再检查实体碰撞和插入路径；`validate` 检查完整模型。validate 的无地面接触、无底部支撑零件报告 `degrees_of_freedom.status=fail, remaining=6`。地面基底固定；保持轴向就位时，单圆接口剩余 1 个偏航自由度，至少两个不同位置接口剩余 0。该自由度模型不证明拔出力或承载。

| 退出码 | 含义 |
|---|---|
| 0 | pass |
| 2 | JSON、参数、未知操作、重复 ID 或坐标与接口冲突 |
| 3 | 零件不存在 |
| 4 | 目标或接口不存在 |
| 5 | 类型、轴线或旋转不支持 |
| 6 | 碰撞或 validate 汇总 fail |
| 7 | 支撑 / 地面错误 |
| 8 | 插入阻挡 / 顺序环 |
| 10 | unknown |

## 分组步骤与导出

支持图来自实际重合的兼容接口，并加入竖直插入路径的先后约束。`order.steps` 保留逐件顺序、`depends_on` 和 `dependency_layer`；`order.grouped_steps` 按**相同依赖层和相同零件原点高度**合并，每步含件数、`add` ID 列表、`new_parts` 零件清单和 `subassembly` 说明。组内逐件安装，不表示这些件可以在空中预拼成独立组件。

导出 `instructions.md`、`steps.json`、LDraw 的 `0 STEP` 和 `scene.json.steps` 都使用分组步骤。`scene.json.piece_steps` 保留逐件数据。另含 assembly、BOM、validation、LDR 与自包含 MPD。scene 含真实 LDraw 顶点、索引、实例位姿和颜色，可直接供 Three.js BufferGeometry 使用；显示时将 +Y 向下转换为向上。export 生成文件并附带 validation；应先检查 validate，不能仅凭写盘成功认定几何通过。

## 重建与测试

```sh
./scripts/rebuild.sh
.venv/bin/pytest tests -q
.venv/bin/python scripts/build_reference.py
.venv/bin/python scripts/render_reference.py
.venv/bin/python -m build --outdir dist
/Users/a123/.hermes/node/bin/npm pack ./plugin --pack-destination plugin
```

首次重建下载官方 complete.zip，后续复用本地快照。本次快照下载于 2026-11-14，HTTP Last-Modified 为 2026-11-09。`build_reference.py` 的每次 add 都使用网格坐标；完整请求/返回保留在 `reference/water-tool/tool-calls.jsonl`，未写入人工位姿。

`reference/water-tool/finished.png`、`front.png`、`top-45.png`、`bottom.png` 和 `cutaway.png` 为 2640×2160。所有砖块来自 `scene.json` 真实三角网格；导出同时递归展开 LDraw type 2 边线与 type 5 条件线。条件线按投影控制点位于端点连线同侧的规则显示，只画前两个端点；所有描边在完整面深度缓冲后进行遮挡测试。颜色直接读取随包官方 `LDConfig.ldr`，平光、细深色线，无渐变背景。

`steps/001.png` 至 `009.png` 为 1280×1100，本步新增件正常着色，已装件淡化，底部附中文步骤、件数与编号清单；`step-parts/001.png` 至 `009.png` 是按本步编号与颜色分组的真实单件网格图标。`steps-contact-sheet.png` 为 1920×1770。剖视保留后半模型，半透明水面使用 `capacity.json` 的 54.70586156433915 mm 水深，图上显示 500 mL / 54.7 mm。

本次 **55 项测试通过**，含验收方 search 空格、×、.dat 归一化与 part .dat 后缀回归，以及边线递归变换、条件线同侧判断和深度遮挡测试。实际输出见 `evidence/pytest-v3.log`；重建与干净环境安装证据见 `evidence/build-package-v3.log`、`evidence/clean-wheel-v3.log`、`evidence/clean-sdist-v3.log`、`evidence/plugin-pack-v3.log`。原有 DSH 实际装配证据继续保留。

## 真实 DSH 小装配

插件使用本机 DSH 的 Cordis `ctx.tools.register`，注册 `lego_search/describe/root/propose/add/validate/order/export` 八个工具，直接调用同一 Python CLI。每个工具的 `request` 是省略 op 的 JSON 参数字符串；接口、错误码与 CLI 一致。

```sh
mkdir -p plugin/packed-v2
tar -xzf plugin/dsh-plugin-ldraw-brick-engine-0.2.0.tgz -C plugin/packed-v2
.venv/bin/python scripts/run_dsh_assembly.py
```

启动器从授权的 CC Switch 存储读取 Codex 的 **SJ / GPT-6-Astra** 配置，凭据只传入子进程环境；使用独立 DSH settings 和空工作目录，不改全局默认模型。实际命令为 `/Users/a123/.hermes/node/bin/dsh --profile headless --patch plugin/assembly-patch.json <prompt>`。插件加载打包 tgz 的解包入口。提示要求底板加至少三块砖、实际触发碰撞 fail 后自行改坐标、validate pass、export。入口记录原始工具事件、完整模型最终回复、压缩会话日志和各次尝试结果；中转失败原文留在 attempt 日志，最多尝试三次。

证据：`evidence/dsh-model-config.json`、`dsh-assembly-prompt.txt`、`dsh-assembly-tools-attempt-*.jsonl`、`dsh-assembly-model-attempt-*.log`、`dsh-assembly-attempts.jsonl`、`dsh-assembly-sessions/`。本次首次尝试完成 1 块 8×8 板加 3 块 2×2 砖；第二块在 `[0,0]` 返回 E_COLLISION，模型改为 `[3,0]` 后成功，validate/export 均 pass。完整 18 次工具调用及返回（含框架参数拒绝和一次 skill 读取）另存 `evidence/dsh-assembly-full-tool-events.jsonl`，验收摘要见 `evidence/dsh-assembly-verification.json` 和 `STATUS.json`。旧版 `dsh-packed-*` 只证明 search，且会话模型实际是 DeepSeek V4 Flash；不作为本次 GPT-6-Astra 装配证据。

## 几何依据与 unknown

递归展开 LDraw type 1 矩阵及 type 3/4 三角面；stud/stud2/stud2a 原语给出顶面凸点，stud3 底销、stud4 底管单独保留证据。接收端候选来自测量外壁和 20 LDU 网格，只接受底部截面满足半径 5.98 LDU 空腔以及至少三个方向接触证据的位置。原点与 grid 由测量外框计算。

碰撞体按全部网格顶点 Y 高度切分为实体截面棱柱，保留空腔、管孔和壁厚；段内 20% / 80% 截面不一致标 unknown。相交面积容差 1e-3 LDU²，位置容差 1e-5 LDU；竖直 +Y 插入用实体扫掠检查。支持绕 Y 的 90° 整数倍刚体旋转。

15 件 unknown：2653、3066、3067a、3067b、3754、4216、4217、48288、6056、6881a、6881b、6934、88393、925、925a。原因包括未识别顶面原语、底部接收端验证不完整、非恒定截面；有网格和来源仍不等于可装配 pass。未覆盖 Technic、斜曲面、侧向接口、夹扣、铰链、套管中心特殊配合、非 90° 姿态、弹性和任意方向插入。未做实体盛水与提起试验。

原始 Author、LICENSE、版本及官方 CAlicense / CAlicense4 / CAreadme 随包保留；本次多数源文件为 CC BY 4.0，按逐件原许可保留署名。软件 MIT；未使用 LDCad shadow 接口数据。
