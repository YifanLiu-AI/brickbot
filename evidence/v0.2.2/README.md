# 0.2.2 验收证据

`prompt.txt` 为原样用户提示；`model.json` 记录 SJ / gpt-6-astra 路由，凭据只通过子进程环境传入。`tool-events.jsonl` 是 BRICK_ENGINE_EVIDENCE 未改写的工具调用/结果，`dsh.log` 是模型最终回复，`report.json` 包含重新读取导出 assembly 后的独立 validate 结果。

成功运行：17 次调用，144.24 秒，一个常驻 Python 进程。catalog 空 category 首次 fail，模型自行改为四个类别继续；此问题已修为把空白 category 当作全部目录，并补充回归。之后 describe ×6 → root → add_batch ×3（20、38、40 件）→ validate pass → export pass。未给模型提供参考装配、预设尺寸、调用顺序或示例方案。

交付为 40 件、6 组步骤。完整导出含 MPD、LDR、scene、BOM、assembly、validation 和说明，存于 report.json 的绝对路径；delivery/ 保留可复核的小文件副本。几何 pass 不证明拔出力、承载强度或实际密封。

测试：全套 61 passed / 1 skipped（未随此仓库发布的旧 dsh 小装配证据）；最后的空类别/导出路径修正后，相关 7 项测试再次通过。packed-plugin.log 检查真实打包入口的 11 个结构化工具、并发序列化、状态增量、回滚、导出、取消和单 worker。installed-wheel.log 检查干净 Python 环境安装的 wheel、包内版本和真实网格导出。

另一次干净包 dsh 复跑在模型首次响应前被 SJ 拒绝：HTTP 429 / INFLIGHT_BALANCE_LIMITED（余额被在途请求预留），0 次工具调用。原始日志保留在本地 ../v0.2.2-wheel-rate-limit/，未将其计作成功。更早的参数 schema 调试失败保留在本地 ../v0.2.2-schema-failure/；直接注册工具必须使用标准 JSON Schema，该问题已修正。
