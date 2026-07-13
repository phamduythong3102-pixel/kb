---
type: FaultCase
id: FC-0087
title: IS-IS组播多拓扑中路由信息不正确
症状实体:
- IS-IS
- 组播多拓扑
- 路由不正确
别名:
  IS-IS:
  - isis
  - ISIS
  组播多拓扑:
  - 组播业务
  - 组播MT
  - IS-IS组播拓扑
  - 组播拓扑
  路由不正确:
  - 路由不对
  - 路由错误
  - 路由有问题
  - 路由学不到
  - 路由信息不正确
涉及命令:
- CMD-display-isis-interface
- CMD-isis-topology-multicast
- CMD-pim-sm
- CMD-display-isis-peer
- CMD-display-isis-route-topology
判据分流:
- step: 1
  检查: 检查IS-IS接口是否加入组播拓扑
  判据: 显示信息中包含字段 IPv4 MT 3
  判据锚点: L15-L25
  否则: ACT-配置接口加入组播拓扑
  满足: goto step 2
  命令: CMD-display-isis-interface
- step: 2
  检查: 检查IS-IS接口的组播拓扑状态是否Up
  判据: IPv4 MT 3 值为 multicast（非 multicast (NO PIM)）
  判据锚点: L31-L31
  否则: ACT-使能PIM-SM
  满足: goto step 3
  命令: CMD-display-isis-interface
- step: 3
  检查: 检查IS-IS的邻居组播拓扑状态是否Up
  判据: MT IDs supported 中包含 3(UP)
  判据锚点: L41-L41
  否则:
    动作: 在对端设备上执行步骤1和步骤2进行检查
    备注: 保证组播拓扑中的所有设备及接口的配置正确，包括产生源路由的接口也同样需要加入IS-IS组播拓扑，并且执行命令 `pim sm` 使能PIM-SM
  满足: goto step 4
  命令: CMD-display-isis-peer
- step: 4
  检查: 检查IS-IS路由表中的组播拓扑路由是否正确
  判据: 路由信息正确
  判据锚点: L51-L53
  否则: goto step 5
  满足: 故障排除
  命令: CMD-display-isis-route-topology
- step: 5
  检查: 收集信息联系技术支持
  动作: 收集上述步骤的执行结果、设备的配置文件、日志信息、告警信息
  判据锚点: L55-L58
source: raw/FC-0087-isis-组播多拓扑路由不正确.md
---

# IS-IS组播多拓扑中路由信息不正确

## 故障处理步骤

#### 背景信息

请保存以下步骤的执行结果，以便在故障无法解决时快速收集和反馈信息。

#### 操作步骤

1. 检查IS-IS接口是否加入组播拓扑

执行 `display isis interface verbose` 命令，查看IS-IS接口是否已经加入组播拓扑。

- 如果显示信息中未包含字段 IPv4 MT 3，则该接口未加入组播拓扑。请在指定接口视图下执行命令 `isis topology multicast`，配置接口加入组播拓扑。

在配置将接口加入组播拓扑之前，需要首先执行：

- 在系统视图下执行命令 `ip topology multicast` 创建组播拓扑。
- 在IS-IS视图下执行命令 `cost-style wide` 或 `cost-style wide-compatible` 修改IS-IS的开销类型。
- 在IS-IS视图下执行命令 `topology topology-name topology-id multicast` 使能IPv4 IS-IS组播拓扑。
- 在接口视图下执行命令 `ip topology multicast enable` 使接口与组播拓扑实例绑定。
- 在接口视图下执行命令 `isis topology multicast` 使能IS-IS接口与IS-IS组播拓扑实例绑定。

- 如果显示信息中包含字段 IPv4 MT 3，则该接口已经加入组播拓扑。请执行步骤2。

2. 检查IS-IS接口的组播拓扑状态是否Up

执行 `display isis interface verbose` 命令，查看IS-IS接口的组播拓扑状态是否Up。

如果显示信息字段 IPv4 MT 3 值为 multicast，则IS-IS接口的组播拓扑状态为Up；如果显示信息字段 IPv4 MT 3 值为 multicast (NO PIM)，则IS-IS接口的组播拓扑状态没有Up。

- 如果IS-IS接口的组播拓扑状态没有Up，请在指定接口视图下执行命令 `pim sm` 使能PIM-SM。

- 如果IS-IS接口的组播拓扑状态已经Up，请执行步骤3。

3. 检查IS-IS的邻居组播拓扑状态是否Up

执行 `display isis peer verbose` 命令，检查IS-IS的邻居组播拓扑状态是否Up。

如果显示信息字段 MT IDs supported 中包含 3(UP)，则IS-IS的邻居组播拓扑状态为Up；否则IS-IS的邻居组播拓扑状态没有Up。其中数字3为IPv4 IS-IS组播拓扑ID。

- 如果IS-IS的邻居组播拓扑状态没有Up，请在对端设备上执行步骤1和步骤2进行检查，保证组播拓扑中的所有设备及接口的配置正确，包括产生源路由的接口也同样需要加入IS-IS组播拓扑，并且执行命令 `pim sm` 使能PIM-SM。

- 如果IS-IS邻居的组播拓扑状态已经Up，请执行步骤4。

4. 检查IS-IS路由表中的组播拓扑路由是否正确

执行 `display isis route topology multicast` 命令，检查IS-IS组播拓扑中的路由信息是否正确。

- 如果路由信息正确，则故障已经排除。

- 如果路由信息不正确，请执行步骤5。

5. 如果故障仍未排除，请收集如下信息，并联系技术支持工程师。

- 上述步骤的执行结果。
- 设备的配置文件、日志信息、告警信息。
