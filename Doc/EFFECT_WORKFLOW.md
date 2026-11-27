# 复杂效果：观察、验收与复用

本分支将场景理解、有限续执行、验收和方案复用接到独立版及 Houdini 内嵌 QML 面板。底层仍使用现有节点、VEX、FX、Skill 和 Bridge 工具；模型请求与工具能力取决于供应商。

## 直接用对话操作

- “先分析当前效果的数据流、属性归属和输出，不要修改” → `get_scene_facts`
- “做一个 32 个点的散布，添加 pscale；检查点数和属性后再结束” → 构建后 `verify_and_summarize`
- “把幅度暴露成一个 0 到 2 的参数” → `create_effect_controls`；不覆盖已有动画或表达式，仅绑定网络内部的浮点参数
- “保留原效果，给我两组不同宽度的方案并分别检查” → `create_effect_variants`；每次最多 4 个独立副本，不切换原显示
- “把这个通过检查的方案记下来，下次复用” → `save_effect_case`，保存前重新检查；`search_effect_cases` 可检索案例
- “把效果副本打包成 HDA，原节点保持可编辑” → `package_effect`；指定命名空间、版本和新的绝对 `.hda` 路径，已有文件不会覆盖

控制参数和变体应使用工具读取到的真实参数路径，不能猜参数名。变体不改源节点；创建失败会清理本次生成的副本。HDA 可能仍依赖外部纹理、缓存或绝对引用，导出前应检查这些依赖。该工具不自动打包所有外部文件。

## 检查什么，怎样判断完成

`get_scene_facts` 提供当前网络连接、非默认参数、显示几何的点/面数量、包围盒、属性的 Point/Primitive/Vertex/Detail 归属，以及 HIP、Houdini 版本、帧和帧范围。默认最多 50 个节点，最多 200 个，并受输出大小限制；`truncated` 表示需要缩小范围继续读取。单位不会凭外观猜测。

写操作后需要 `verify_and_summarize` 的新结果。工具返回的 `success` 表示检查执行完成，`validation.status` 才是 `passed`、`failed` 或 `unverified`。仅结构检查通过不计作本轮效果验收；需要声明 `criteria`。

```json
{
  "network_path": "/obj/effect",
  "check_items": ["/obj/effect/OUT"],
  "expected_result": "32 个点且存在点属性 pscale",
  "criteria": [
    {"kind": "point_count", "node_path": "/obj/effect/OUT", "min": 32, "max": 32},
    {"kind": "attribute", "node_path": "/obj/effect/OUT", "owner": "point", "name": "pscale"}
  ]
}
```

支持节点存在、输入连接、参数值/范围、点数、面数、包围盒轴向大小、属性存在及位置有限值检查。数值条件需提供上下界之一，参数也可指定精确 `value`。可用 `frames` 检查采样帧，每条最多 120 帧、每次最多 50 条；结束后恢复原帧。无连接分支只告警，因为源节点或辅助分支可以合法存在。

这些检查不能自动证明审美质量、整段模拟无穿插、运动稳定或性能达标。帧采样也不能替代完整缓存/仿真验证。模型须报告检查范围；未支持的条件标记为未验证。

Agent 和经确认的 Plan 执行阶段会检测提前总结，最多追加 3 次续执行提醒；连续无进展会停止。每轮最多 80 次模型迭代、200 次工具调用；工具执行前也检查 15 分钟的时间预算。此预算不会强制中断已经进入 Houdini 的单次 Cook。Ask 和 Plan 调研阶段不会自动执行计划。

如果仍有待办步骤、缺少新验收或检查失败，本轮会明确提示“尚未通过验收”，保留当前结果并暂停待发送消息队列。可以继续要求修改，或手动继续队列。验收报告随聊天历史保存，恢复聊天不自动执行旧计划。

## 案例与场景状态

保存案例需要用户要求，并且现场重新检查通过。案例记录方案说明、步骤、条件、版本与来源 HIP；它们是参考数据，不执行存储的任意代码。项目案例只在指定相同 `project` 时检索；空项目表示通用案例。版本不同时返回 `version_match: false`，复用后仍需重新验收。

源码运行的案例数据库位于 `cache/effect_library/cases.db`。安装版或独立安装的 Bridge 使用用户目录 `HoudiniAgent/effect_library/cases.db`；独立版通过自身入口保存和查询，避免写到另一个 Bridge 副本。开启长期记忆时会自动检索通用案例；关闭时不自动注入。显式查询/保存案例可由用户单独要求。

上次场景观察只保留精简摘要，并明确标记可能过期。换 HIP、切换会话或手动改图后，应重新读取，再做写操作；缓存摘要不能当作当前场景事实。

右上角 Houdini 菜单的会话项悬浮时显示 HIP 名称和完整路径。未保存场景会标为“未保存场景”；加载、保存和清空场景后更新元数据，下次刷新会话列表可见。旧 Bridge 不提供项目元数据，需要更新集成包并重启对应 Bridge/Houdini；列表仍兼容旧会话。

## 真实 HIP 回归

使用 Houdini 自带的 `hython`，在独立进程运行，避免载入用户当前场景：

```bash
hython tools/benchmark_effects.py smoke --report cache/effects-smoke.json
hython tools/benchmark_effects.py prepare --directory cache/effect-benchmarks
```

`smoke` 在内存中检查参数绑定、表达式保护、独立变体、原网络保留、临时 HDA 导出、错误检测和恢复原帧。`prepare` 写出 4 个未完成的 HIP 与任务 JSON：盒子尺寸、Detail Wrangle 点生成、动画包围盒、点散布和属性；已有夹具不覆盖。

让 Agent 按对应 JSON 中的 `prompt` 修改 HIP，另存输出，然后独立验收：

```bash
hython tools/benchmark_effects.py evaluate \
  --hip cache/effect-benchmarks/box_scale_completed.hip \
  --task cache/effect-benchmarks/box_scale.json \
  --report cache/box-scale-result.json
```

验收失败/未验证时返回非零退出码。脚本不调用模型：集成测试通过不等于 LLM 任务成功率。真实复杂 RBD/FLIP/Pyro、碰撞与跨版本资产回归仍需补充具体场景和可测标准。
