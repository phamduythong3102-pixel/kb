---
type: FaultCase
id: FC-0100
title: 设备学习不到预期的IS-IS路由
症状实体:
- IS-IS
- IS-IS路由
- 路由不正确
别名:
  IS-IS:
  - isis
  - ISIS
  IS-IS路由:
  - ISIS路由
  - 指定路由
  - 预期路由
  路由不正确:
  - 路由不对
  - 路由错误
  - 路由有问题
  - 路由学不到
  - 学习不到路由
  - 路由缺失
  - 路由信息不正确
涉及命令:
- CMD-display-ip-routing-table
- CMD-display-isis-peer
- CMD-display-isis-route
- CMD-display-isis-lsdb
- CMD-display-current-configuration-configuration-isis
判据分流:
- step: 1
  检查: 检查设备路由学习状态，确认设备是否无法学习到IS-IS路由
  命令: CMD-display-ip-routing-table
  判据: IP路由表中是否存在协议优先级比IS-IS高的路由
  判据锚点: L16-L49
  否则:
    动作: IP路由表中存在协议优先级比IS-IS高的活跃路由，请根据网络规划调整配置
  满足: goto step 2
- step: 2
  检查: 检查IS-IS邻居是否正常建立
  命令: CMD-display-isis-peer
  判据: IS-IS邻居是否都正常建立
  判据锚点: L53-L65
  否则:
    动作: 有邻居没有正常建立，请参见 IS-IS邻居无法建立的定位思路
  满足: goto step 3
- step: 3
  检查: 检查IS-IS路由表是否存在指定路由
  命令: CMD-display-isis-route
  判据: IS-IS路由表中指定路由是否存在
  判据锚点: L69-L106
  否则: goto step 4
  满足: goto step 8
- step: 4
  检查: 检查接收端LSDB中是否携带指定路由网段
  命令: CMD-display-isis-lsdb
  判据: IS-IS泛洪的LSP报文中是否携带对应路由网段
  判据锚点: L85-L104
  否则: goto step 6
  满足: goto step 5
- step: 5
  检查: 检查接收端的IS-IS配置是否正确
  判据: 接收端的IS-IS配置是否正确，如是否有路由过滤、认证是否和发送端一致
  判据锚点: L108-L108
  否则:
    动作: 配置有误，请根据实际需要视情况修改接收端IS-IS配置（路由过滤、认证等）
  满足: goto step 6
- step: 6
  检查: 检查指定的IS-IS路由是否发布
  命令: CMD-display-isis-lsdb
  判据: LSP报文中是否携带了指定路由
  判据锚点: L144-L181
  否则:
    动作: 检查源端设备配置是否正确，例如接口是否使能IS-IS；如果是引入的外部路由，执行 `display ip routing-table` protocol
      protocol verbose 命令查看外部路由是否是活跃的
  满足: goto step 7
- step: 7
  检查: 检查IS-IS的数据库是否同步
  命令: CMD-display-isis-lsdb
  判据: LSDB数据库中是否存在指定的LSP报文，且 Seq Num 是否与本地一致
  判据锚点: L183-L190
  否则:
    动作: 若LSDB数据库中不存在指定的LSP报文，排查设备底层和中间链路是否存在故障；若存在但 Seq Num 与本地不一致且不停增长，说明网络中存在其他设备与发布指定路由的设备System
      ID配置相同，需排查网络中设备的IS-IS配置；若 Seq Num 不一致且一直保持不变，可能是LSP报文在传输过程中被丢弃，需排查设备底层和中间链路是否存在故障
  满足: goto step 8
- step: 8
  检查: 检查中间设备是否处于overload状态
  命令: CMD-display-isis-lsdb
  判据: 设备发布的LSP里是否有overload标记位（ATT/P/OL中OL值为1）
  判据锚点: L192-L216
  否则:
    动作: 登录对应设备，通过 `display current-configuration configuration isis` 命令确认是否有 set-overload
      配置；若存在非预期配置，请删除
  满足: goto step 9
- step: 9
  检查: 收集信息联系技术支持
  判据锚点: L218-L221
  动作: 收集上述步骤的执行结果、设备的配置文件、日志信息、告警信息
source: raw/NE40E 维护宝典/故障处理：IP路由/IS-IS故障案例/故障案例：设备学习不到预期的IS-IS路由/故障处理步骤.md
常见原因:
- 其它路由协议也发布了相同的路由，并且路由协议优先级比IS-IS协议高
- 引入的外部路由优先级低，没有被优选
- IS-IS邻居没有正常建立
- IS-IS配置问题，比如：两端设备cost-style不匹配、认证类型不匹配、路由策略配置问题等
- 设备底层故障或者链路故障，造成LSP报文丢失
相关告警:
- ISIS_1.3.6.1.3.37.2.0.17 isisAdjacencyChange
- ISIS_1.3.6.1.4.1.2011.5.25.24.2.4.49 hwIsisSystemIdCfgConflict
相关日志:
- ISIS/2/ISIS_ID_LEN_MISMATCH
- ISIS/3/ISIS_AREA_MISMATCH
- ISIS/3/ISIS_AUTHENTICATION_FAILURE
- ISIS/3/ISIS_AUTHENTICATION_TYPE_FAILURE
- ISIS/3/ISIS_REJECTED_ADJACENCY
- ISIS/4/IS_RECV_ERR_PKT
- ISIS/5/IS_ADJ_CHANGE
- ISIS/5/IS_CIRC_STATE_SET
- ISIS/6/IS_REMOTE_SYS_ID_CONFLICT
- ISIS/6/ISIS_SYS_ID_CONFLICT
补充来源:
- raw/NE40E 维护宝典/故障处理：IP路由/IS-IS故障案例/故障案例：设备学习不到预期的IS-IS路由/常见原因.md
- raw/NE40E 维护宝典/故障处理：IP路由/IS-IS故障案例/故障案例：设备学习不到预期的IS-IS路由/相关告警与日志.md
---

# 故障处理步骤

## 背景信息

执行命令完成故障处理操作后，请根据系统中的配置生效模式，确保配置下发。如无特殊说明，本手册采用配置立即生效模式进行描述。

- 配置立即生效模式下，输入命令行并键入回车键后，配置将立即生效。
- 配置两阶段生效模式下，请在完成配置后，执行命令 `commit` ，提交配置。

请保存以下步骤的执行结果，以便在故障无法解决时快速收集和反馈信息。

## 操作步骤

1. 检查设备路由学习状态，确认设备是否无法学习到IS-IS路由

通过 `display ip routing-table` ip-address [ mask | mask-length ]命令，逐跳查看路由表信息，确认路径上第一台没有学习到IS-IS路由的设备。在此设备上执行 `display ip routing-table` ip-address [ mask | mask-length ] verbose 命令查看IP路由表中是否存在协议优先级比IS-IS高的路由。

```
[~HUAWEI] display ip routing-table 10.1.1.94 
Route Flags: R - relay, D - download to fib, T - to vpn-instance, B - black hole route
------------------------------------------------------------------------------
Routing Table : _public_
Summary Count : 1

Destination/Mask    Proto   Pre  Cost        Flags NextHop         Interface

      10.1.1.94/32  ISIS-L2  15   110           D   10.95.96.1      GigabitEthernet1/0/0
[~HUAWEI] display ip routing-table 10.1.1.94 verbose  
Route Flags: R - relay, D - download to fib, T - to vpn-instance, B - black hole route
------------------------------------------------------------------------------
Routing Table : _public_
Summary Count : 1

Destination: 10.1.1.94/32         
     Protocol: ISIS-L2             Process ID: 1111           
   Preference: 15                        Cost: 110            
      NextHop: 10.95.96.1          Neighbour: 0.0.0.0
        State: Active Adv                 Age: 1d15h16m11s         
          Tag: 0                    Priority: high           
        Label: NULL                  QoSInfo: 0x0           
   IndirectID: 0x100017C            Instance:                                 
 RelayNextHop: 0.0.0.0             Interface: GigabitEthernet1/0/0
     TunnelID: 0x0                     Flags: D
```

State 字段为 Active Adv 表示该路由为活跃的路由，如果存在相同前缀的多个协议的路由，协议优先级高的路由优选为活跃的路由。

- 如果存在，请根据网络规划调整配置。
- 如果不存在，请执行步骤2。

2. 检查IS-IS邻居是否正常建立

在路径上的每一台设备上执行 `display isis peer` ，查看IS-IS邻居是否都正常建立。

```
[~HUAWEI] display isis peer   
                          Peer information for ISIS(1111)

  System Id     Interface          Circuit Id        State HoldTime Type     PRI
--------------------------------------------------------------------------------
1492.2624.1095* GE1/0/0            0000000262         Up    28s      L2       --
```

- 如果有邻居没有正常建立，请参见 IS-IS邻居无法建立的定位思路。
- 如果邻居正常建立，请执行步骤3。

3. 检查IS-IS路由表是否存在

执行 `display isis route` 命令，查看IS-IS路由表，检查IS-IS路由是否存在。

```
[~HUAWEI] display isis route 10.1.1.94 
                         Route information for ISIS(1111)
                         -----------------------------
                        ISIS(1111) Level-2 Forwarding Table
                        --------------------------------
IPV4 Destination   IntCost    ExtCost ExitInterface     NextHop         Flags
-------------------------------------------------------------------------------
10.1.1.94/32        110        NULL    GE1/0/0           10.95.96.1      A/-/-/-
     Flags: D-Direct, A-Added to URT, L-Advertised in LSPs, S-IGP Shortcut, 
            U-Up/Down Bit Set, LP-Local Prefix-Sid
     Protect Type: L-Link Protect, N-Node Protect
```

- 如果不存在，请在路由接收端通过命令 `display isis lsdb verbose | include x.x.x.x` 检查IS-IS泛洪的LSP报文中是否携带对应路由网段（其中 x.x.x.x 为学习不到的路由IP）。

  ```
  [~HUAWEI] display isis 1111 lsdb verbose | include 10.1.1.94 
  Info: It will take a long time if the content you search is too much or the string you input is too long, you can press CTRL_C to break.
                          Database information for ISIS(1111)
                          -----------------------------------
                            Level-2 Link State Database
  LSPID                  Seq Num    Checksum   HoldTime       Length   ATT/P/OL
  -----------------------------------------------------------------------------
   INTF ADDR    10.1.1.94
  +IP-Extended  10.1.1.94        255.255.255.255  COST: 0          
   Router ID    10.1.1.94
   Router Cap   10.1.1.94         D: 0  S: 0
  Total LSP(s): 4
      *(In TLV)-Leaking Route, *(By LSPID)-Self LSP, +-Self LSP(Extended),
             ATT-Attached, P-Partition, OL-Overload
  ```

  如果携带说明路由源已发布该路由，请执行步骤4；如果没有携带请执行步骤5。

- 如果存在，请执行步骤7。

4. 检查接收端的IS-IS配置是否正确，如是否有路由过滤、认证是否和发送端一致等，如果配置有误，请根据实际需要视情况修改。如果不能解决，请执行步骤5。

```
[~HUAWEI] display current-configuration configuration isis 1111 
#
isis 1111
 is-level level-2
 cost-style wide
 timer lsp-generation 1 50 50 level-2
 bfd all-interfaces enable
 bfd all-interfaces min-tx-interval 150 min-rx-interval 150 frr-binding
 network-entity 86.5235.0001.1492.2624.1096.00
 avoid-microloop frr-protected
 avoid-microloop frr-protected rib-update-delay 5000
 is-name R96
 filter-policy ip-prefix 94 import 
 domain-authentication-mode hmac-sha256 key-id 1 cipher %^%#&D#{I|Kt6#BYnJWJcx51uJ1H:n\|P"(bv.48r_W%^%# 
 timer spf 1 50 50
 traffic-eng level-2
 set-overload on-startup 20
 frr
  loop-free-alternate level-2
 #
 ipv6 enable topology ipv6
 ipv6 advertise link attributes
 ipv6 bfd all-interfaces enable
 ipv6 bfd all-interfaces min-tx-interval 150 min-rx-interval 150 frr-binding
 ipv6 traffic-eng level-2
 segment-routing ipv6 locator pe
 ipv6 frr
  loop-free-alternate level-2
  ti-lfa level-2
 #
#
```

5. 检查指定的IS-IS路由是否发布

在路由源设备上，执行 `display isis lsdb` verbose local ，查看本地产生的LSP报文中是否携带了指定路由。

```
<HUAWEI> display isis 1111 lsdb verbose local  
                        Database information for ISIS(1111)
                        -----------------------------------
                          Level-2 Link State Database

LSPID                  Seq Num    Checksum   HoldTime       Length   ATT/P/OL
-----------------------------------------------------------------------------
1492.2624.1094.00-00*  0x000000db 0x2936     397            905      0/0/0   
 SOURCE       R94.00 
 HOST NAME    R94
 NLPID        IPV4
 NLPID        IPV6
 AREA ADDR    86.5235.0001
 INTF ADDR  10.1.1.94 
 INTF ADDR    10.1.94.102
 INTF ADDR    10.46.101.94
 INTF ADDR    10.0.0.1
 INTF ADDR    10.94.95.1
 INTF ADDR    10.102.1.1
 INTF ADDR    10.102.0.1
 INTF ADDR V6 2001:DB8::94
 Topology     Standard, IPV6
+NBR  ID      R95.00  COST: 100
+NBR  ID      R102.00  COST: 100
+NBR  ID      R102.00  COST: 10
..
Total LSP(s): 1
    *(In TLV)-Leaking Route, *(By LSPID)-Self LSP, +-Self LSP(Extended),
           ATT-Attached, P-Partition, OL-Overload
```

- 如果LSP报文中没有携带指定的路由，请检查源端设备配置是否正确，例如接口是否使能IS-IS。如果是引入的外部路由，执行 `display ip routing-table` protocol protocol verbose 命令查看外部路由是否是活跃的。
- 如果LSP报文中携带了指定的路由，请执行步骤6。

6. 检查IS-IS的数据库是否同步

在学习不到IS-IS路由的设备上，执行 `display isis lsdb` ，查看是否收到发布指定路由的设备的LSP报文。其中，LSPID 是一条LSP的标识，Seq Num 是报文的序列号，序列号越大表示报文越新。

- 如果LSDB数据库中不存在指定的LSP报文，请排查设备底层和中间链路是否存在故障。
- 如果LSDB数据库中存在指定的LSP报文，但 Seq Num 与 `display isis lsdb` local verbose 命令显示的不一致，并且 Seq Num 不停的增长，则网络中存在其他设备与发布指定路由的设备的System ID配置相同，请排查网络中设备的IS-IS配置。
- 如果LSDB数据库中存在指定的LSP报文，但 Seq Num 不一致，并且一直保持不变，可能是LSP报文在传输过程中被丢弃，请排查设备底层和中间链路是否存在故障。
- 如果LSDB数据库中存在指定的LSP报文，并且 Seq Num 一致，请执行步骤7。

7. 检查中间设备是否处于overload状态，并检查携带overload标记设备的配置，如果路径设备携带overload标记且无备用路由会导致路由路径无法计算成功

通过 `display isis lsdb` 命令，查看设备发布的LSP里是否有overload标记位（ATT/P/OL中OL值为1），并查看对应的LSPID。

```
[~HUAWEI] display isis 1111 lsdb  
                        Database information for ISIS(1111)
                        -----------------------------------
                          Level-2 Link State Database
LSPID                 Seq Num      Checksum      HoldTime      Length  ATT/P/OL 
-------------------------------------------------------------------------------
R94.00-00             0x000000e0   0x1f3b        1136          905     0/0/0   
R95.00-00             0x000000da   0x21f4        1156          548     0/0/1    
R96.00-00*            0x000000d8   0xd234        1134          448     0/0/0   
R102.00-00            0x000000d5   0x4cc9        1136          593     0/0/0   

Total LSP(s): 4
    *(In TLV)-Leaking Route, *(By LSPID)-Self LSP, +-Self LSP(Extended),
           ATT-Attached, P-Partition, OL-Overload
```

- 如果有overload标记，则登录对应设备，通过 `display current-configuration configuration isis` 命令确认是否有set-overload配置。
  - 如果存在，请确认配置原因，是否是预期配置，如果非预期配置请删除。
  - 如果不存在，请执行步骤8。
- 如果没有overload标记，请执行步骤8。

8. 如果故障仍未排除，请收集如下信息，并联系技术支持工程师。

- 上述步骤的执行结果。
- 设备的配置文件、日志信息、告警信息。
