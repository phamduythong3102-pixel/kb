---
type: Action
id: ACT-配置接口加入IPv6单播拓扑
命令序列:
- 视图: 指定接口视图
  命令: isis ipv6 enable
requires:
- order: 1
  视图: 系统视图
  命令: ipv6
- order: 2
  视图: 接口视图
  命令: ipv6 enable
- order: 3
  视图: IS-IS视图
  命令: cost-style wide
- order: 4
  视图: IS-IS视图
  命令: topology ipv6-unicast
- order: 5
  视图: 接口视图
  命令: isis ipv6 enable
被引用于:
- FC-0092
source: raw/FC-0092-isis-ipv6单播多拓扑路由不正确.md
requires锚点: L19-L23
---
# 配置接口加入IPv6单播拓扑

在配置将接口加入IPv6单播拓扑之前，需要首先执行：

- 在系统视图下执行命令 `ipv6` 使能设备的IPv6报文转发功能。
- 在接口视图下执行命令 `ipv6 enable` 使能接口的IPv6功能。
- 在IS-IS视图下执行命令 `cost-style wide` 或 `cost-style wide-compatible` 修改IS-IS的开销类型。
- 在IS-IS视图下执行命令 `topology ipv6-unicast` 使能IPv6单播拓扑。
- 在接口视图下执行命令 `isis ipv6 enable` 使能IS-IS接口与IPv6单播拓扑实例绑定。
