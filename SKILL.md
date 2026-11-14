---
name: brickbot
description: Assemble geometry-verified rectangular LEGO parts with local integer grid connectors, validate, group instructions and export through CLI or DSH.
---

# 乐高装配核心 0.2.1

安装 `dist/ldraw_brick_engine-0.2.1-py3-none-any.whl`；任意能执行命令的 agent 可调用 `brick-engine`。每次输入一个 JSON 对象，返回一个 JSON 对象；0=pass，10=unknown，其余为错误。109 件中 94 件完整验证、15 件 unknown，共 13,327 个已提取接口。

1. `search` 找件；`describe` 查尺寸、网格和状态。只使用 `validation.status=pass` 的件。接口多于 64 个默认精简，强制精简用 `compact:true`；需要逐个接口证据时用 `compact:false`。
2. `root` 创建地面基底。+Y 向下，1 LDU=0.4 mm。
3. `add` 提供目标实例 `target`、目标凸点 `target_stud:[列,行]`、新件接收端 `anchor:[列,行]`。坐标均为整数，从 0 开始，局部最小 X/Z 的凸点中心为原点，列向 +X，行向 +Z，间距 20 LDU；坐标在旋转前定义。范围看 `grid.column_range/row_range`，不要从零件名称猜 X/Z 长度。rotation 为 0/90/180/270。
4. 保存工具返回的完整 assembly，再原样传给下一次操作；不要手改 position。`propose` 只解位姿；`add` 才检查碰撞与插入。fail 后按 reason/suggestion 改坐标或旋转，失败不会添加零件；unknown 不等于 pass。
5. `validate` 检查整体。无支撑悬空件 DOF 为 fail / remaining 6；固定地面为 0，保持轴向就位的单圆接口为 1，至少两个不同位置接口为 0。承载与防水单独标 unknown。
6. `order.steps` 是逐件依赖；`grouped_steps` 把同依赖层、同高度件合并，每步有件数、清单和子装配说明。`export` 的 instructions.md、LDraw STEP、scene.steps 均使用分组步骤。先确认 validate pass，再交付导出物。

旧接口写法 `target_interface:"sN", interface:"aN"` 保留。序号由原始几何遍历决定，并非对应网格：**3001 的 s0→a0 会沿 +X 错三格、沿 +Z 错一格**。同型号零旋转齐边叠放用 `target_stud:[0,0], anchor:[0,0]`；不同尺寸件这样对齐的是最小 X/Z 凸点，不是中心。同时给序号和网格时，二者必须一致。

完整 CLI 状态传递示例：

```sh
python3 -m venv .lego-venv
.lego-venv/bin/pip install /ABSOLUTE/PATH/core/dist/ldraw_brick_engine-0.2.1-py3-none-any.whl
.lego-venv/bin/python <<'PY'
import json, subprocess
from pathlib import Path
cli = str(Path('.lego-venv/bin/brick-engine').resolve())
def call(request):
    p = subprocess.run([cli], input=json.dumps(request), text=True, capture_output=True)
    result = json.loads(p.stdout)
    if p.returncode: raise RuntimeError(result)
    return result
print(call({'op':'describe','part':'91405'}))
a = call({'op':'root','part':'91405','id':'base'})['assembly']
for n,c in enumerate((0,6,12)):
    a = call({'op':'add','assembly':a,'part':'3001','target':'base',
              'target_stud':[c,0],'anchor':[0,0],'rotation':0,
              'id':f'brick{n+1}','structure':'wall','color':7})['assembly']
print(call({'op':'validate','assembly':a}))
print(call({'op':'order','assembly':a}))
print(call({'op':'export','assembly':a,'directory':'lego-output'}))
PY
```

参考工具：65 件，9 个分组步骤，内腔容量 644.637 mL；两只对称夹层握持耳各有上下 16 个接口连接，转角逐层交错。调用记录 `reference/water-tool/tool-calls.jsonl`；重建 `.venv/bin/python scripts/build_reference.py`，渲染 `.venv/bin/python scripts/render_reference.py`。

DSH：`lego_search/describe/root/propose/add/validate/order/export` 的 `request` 参数为上述 JSON 参数对象的**字符串**，省略 op。例如：

```json
{"request":"{\"part\":\"91405\",\"compact\":true}"}
```

这是 lego_describe 的参数。零件编号用 `3001`，不带 `.dat`。真实 GPT-6-Astra 中转小装配验收运行 `.venv/bin/python scripts/run_dsh_assembly.py`，加载 tgz 解包入口，完整 fail→修正与最终回复见 `evidence/dsh-assembly-*`，本次实际小装配为 1 板加 3 砖，第二块从 `[0,0]` 碰撞改为 `[3,0]` 后 pass，验证和导出 pass；完整事件见 `evidence/dsh-assembly-full-tool-events.jsonl`。51 项回归测试通过，验收状态见 STATUS.json。
