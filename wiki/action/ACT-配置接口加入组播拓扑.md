---
type: Action
id: ACT-配置接口加入组播拓扑
命令序列:
- 视图: 指定接口视图
  命令: isis topology multicast
requires:
- order: 1
  视图: 系统视图
  命令: ip topology multicast
- order: 2
  视图: IS-IS视图
  命令: cost-style wide
- order: 3
  视图: IS-IS视图
  命令: topology topology-name topology-id multicast
- order: 4
  视图: 接口视图
  命令: ip topology multicast enable
- order: 5
  视图: 接口视图
  命令: isis topology multicast
被引用于:
- FC-0087
source: raw/FC-0087-isis-组播多拓扑路由不正确.md
requires锚点: L19-L23
---
# 配置接口加入组播拓扑

在配置将接口加入组播拓扑之前，需要首先执行：

- 在系统视图下执行命令 `ip topology multicast` 创建组播拓扑。
- 在IS-IS视图下执行命令 `cost-style wide` 或 `cost-style wide-compatible` 修改IS-IS的开销类型。
- 在IS-IS视图下执行命令 `topology topology-name topology-id multicast` 使能IPv4 IS-IS组播拓扑。
- 在接口视图下执行命令 `ip topology multicast enable` 使接口与组播拓扑实例绑定。
- 在接口视图下执行命令 `isis topology multicast` 使能IS-IS接口与IS-IS组播拓扑实例绑定。
