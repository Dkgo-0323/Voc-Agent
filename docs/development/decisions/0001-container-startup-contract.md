# 0001：隔离容器交付与启动契约

- 日期：2026-10-21；状态：已确认。用户在当日新聊天明确“确认今日方案A”，实施开始复查时间约 21:20 北京时间。
- 关联：[当日规划与实施回填](../daily/2026-10-21.md)。

## 背景

双端 CI 与 wheel 已验收，但根 Compose 仅启动存储，API 启动还依赖迁移、锁定 SKU、Milvus 和 embedding 维度检查。旧容器与卷正在运行，必须保护现有数据。

## 决策

1. Python 3.12 锁定运行依赖与 wheel，API/worker 共镜像、独立进程，非 root。迁移由镜像内 Alembic 读取已安装 wheel 资源；不挂载源码或本地 `.env`。
2. Node 22 构建 Next.js standalone 并补齐静态资源。浏览器 API URL 是构建参数，默认回环端口；改域名须重新构建。
3. ops 独立 Compose 使用独立项目名和卷，无固定全局容器名；存储健康后由一次性 init 执行迁移和基础 seed，成功后 API/可选 worker 才启动。worker 默认关闭、显式 profile 选择，保持 APScheduler 单实例。
4. 默认本机回环绑定。专用 smoke 覆盖文件启用明确标识的 embedding 测试服务与内部网络，不访问真实 provider；保留真实生产维度检查，验证 1024 维成功和 768 维拒绝。仅测试依赖下的启动闭环，不证明语义效果或完整真实业务链路。
5. 真实 provider、付费、凭据配置、生产 CORS/HTTPS/访客限额和公网发布不在本次确认范围。

## 备选与后果

- 仅镜像更小，但不能验证初始化依赖；用户确认了包含编排/启动烟测的 A。
- 同源代理或运行时 API URL 注入增加部署灵活性，也增加本次范围；留待公网设计。
- 测试 provider 无需真实密钥且可重复触发错误；不能把测试向量用于真实检索，不能替代 ENG-05B。
- 不升级现有 Milvus/Postgres 或引入队列、Agent 框架；不对旧卷执行迁移/seed/清理。

## 实施发现：MinIO 旧镜像已不可拉取

首次完整 Linux CI 因旧 `minio/minio:RELEASE.2023-03-13T19-46-17Z` pull denied 失败，同标签 Quay manifest 也不存在。核对 [Milvus 官方开发 Compose](https://github.com/milvus-io/milvus/blob/06dec9a0e063aa9853da2000e555888fb491cb39/deployments/docker/dev/docker-compose.yml) 后，新 ops 编排改用其维护的 `milvusdb/minio:RELEASE.2024-12-18T13-15-44Z` 和 `mc ready local` 健康检查。这是新隔离环境的兼容性修复，不改变根 Compose、旧 MinIO、Milvus/Postgres 版本或任何旧卷。兼容性必须由实际 smoke 验证，不能仅凭上游使用记录认定通过。

## 实施发现：internal 网络与宿主机测试入口

第二次 Linux smoke 的应用内启动/健康检查成功，但直接映射 internal 网络端口的宿主机请求被拒绝。保留 API/worker/provider 仅连接内部网络，smoke 专用固定目标转发器同时接内部网络和回环入口网络，只转发 API/web 两个预定目标；不支持任意代理目的地、CONNECT 或生产流式服务。Compose smoke 覆盖通过 `ports: !reset []` 清除应用直映射，转发器是唯一回环发布入口；普通编排和前端 build-time URL 方案不增加网关。该测试辅助不替代未来生产代理/HTTPS 设计。
