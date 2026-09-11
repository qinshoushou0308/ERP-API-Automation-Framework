# GitHub Actions 持续集成

项目把回归测试分成两层，避免云端任务依赖个人电脑上的服务。

## 1. Framework Regression

文件：`.github/workflows/framework-regression.yml`

- 触发方式：推送代码、创建或更新 Pull Request、手动运行。
- 运行环境：GitHub 提供的 Ubuntu 云端运行器。
- 执行内容：安装 Python 和依赖，启动仓库内的 Mock 服务，等待健康检查通过，然后执行 `tests/unit` 与 `testcase`。
- 测试证据：无论成功或失败，均保存 Allure 原始结果和 Mock 服务日志 14 天。
- 失败处理：任意测试失败，整个工作流失败，可作为代码合并前的质量门禁。

## 2. ERP Regression

文件：`.github/workflows/erp-regression.yml`

- 触发方式：手动运行，并在启动时选择要执行的测试范围。
- 运行环境：安装在本机 Windows 上、带有 `erp-local` 标签的 GitHub self-hosted runner。
- 前置条件：本机 ERP、MySQL 和 Redis 已经启动，ERP 监听 `127.0.0.1:9999`。
- 执行内容：先检查 ERP 端口，再按所选标签执行 `erp_tests` 中的采购与库存测试。
- 并发策略：同一时间只运行一组 ERP 回归，避免多个任务同时修改同一套测试数据。
- 测试证据：保存 Allure 原始结果与完整 HTML 报告 14 天。
- 在线报告：测试成功后发布到 [GitHub Pages](https://qinshoushou0308.github.io/ERP-API-Automation-Framework/)。
- 历史趋势：按测试范围分别保存 Allure 历史数据，可查看通过率、执行时间和用例稳定性变化。
- 失败通知：自动创建 GitHub Issue，附带测试范围、提交号、运行链接和报告产物名称。

ERP 流程没有放到 GitHub 公共运行器，是因为公共运行器访问不到本机服务和数据库。把 runner 安装到本机后，GitHub 页面上的任务会在本机执行。

运行 ERP 工作流时可以选择：

- `all`：5 条 ERP 用例全部执行。
- `smoke`：快速验证登录和采购订单查询，不修改 ERP 业务数据。
- `regression`：执行采购订单、采购入库和异常规则三条完整业务测试。
- `negative`：只验证重复审核、违规删除、超量入库等异常规则。
- `inventory`：只验证采购入库引起库存变化并在清理后恢复。

ERP 用例还使用 `p0`、`p1`、`p2` 标记优先级，其中 `p0` 是发布阻断级核心路径。

Pages 只发布最近一次成功执行的报告。失败执行仍会保留可下载的 Allure HTML 产物，并通过 Issue 通知，避免失败报告覆盖最后一份健康报告。

## 首次接入步骤

1. 在自己的 GitHub 账号创建仓库，或 Fork 原始项目。
2. 把本地仓库的远程地址改成自己的仓库并推送代码。
3. 打开仓库的 `Actions` 页面，`Framework Regression` 会自动开始。
4. 如需从 GitHub 运行 ERP 测试，在仓库 `Settings -> Actions -> Runners` 中添加 Windows self-hosted runner。
5. 给该 runner 增加 `erp-local` 标签，并在运行 ERP 流程前启动 ERP、MySQL 和 Redis。

## 本地等价命令

Mock 服务已经运行时：

```powershell
uv run --frozen --no-sync pytest -q ./tests/unit ./testcase --alluredir=./report/local-ci-allure-results --clean-alluredir
```

ERP 服务已经运行时：

```powershell
uv run --frozen --no-sync pytest -q ./erp_tests --alluredir=./report/local-ci-erp-allure-results --clean-alluredir
```

本地也可以按标签选择用例，例如：

```powershell
uv run --frozen --no-sync pytest -q ./erp_tests -m smoke
uv run --frozen --no-sync pytest -q ./erp_tests -m negative
uv run --frozen --no-sync pytest -q ./erp_tests -m p0
```
