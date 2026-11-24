# realworld-api-test

对开源项目 [RealWorld（Conduit）](https://github.com/realworld-apps/realworld) 的接口自动化测试实践。

**被测实现**：[`nsidnev/fastapi-realworld-example-app`](https://github.com/nsidnev/fastapi-realworld-example-app)（FastAPI + SQLAlchemy + PostgreSQL）

---

## 一、做了什么

| 项 | 内容 |
|---|---|
| 接口清单 | 依据官方 `openapi.yml` 整理 **19 个接口**，分 6 个模块 |
| 测试用例 | **101 条**，覆盖正向 / 逆向 / 边界 / 幂等 / 鉴权 / 一致性 |
| 自动化 | pytest + requests，**109 个测试**（101 条数据驱动 + 8 条手工编写） |
| 缺陷报告 | **6 份**正式缺陷 + **3 组**系统性偏差分析 |
| 执行方式 | 数据参数化，可无限次重复运行 |

**当前结果**：`76 passed, 33 xfailed`（xfail 是已登记的已知问题，见 `known_issues.py`）

---

## 二、目录结构

```
realworld-api-test/
├── conftest.py            pytest 夹具（token / 文章 / 评论）
├── case_engine.py         用例引擎：CSV -> HTTP 请求
├── known_issues.py        已知问题登记表
├── data/
│   └── cases.csv          101 条用例（从 Excel 用例表导出）
├── docs/
│   ├── 缺陷报告.md         6 份正式缺陷 + 3 组系统性偏差
│   └── 执行报告.md         执行过程与失败归因
├── tests/
│   ├── test_api_cases.py  数据驱动主套件
│   ├── test_destructive.py 破坏性用例（独立数据）
│   └── test_smoke.py      业务冒烟（断言响应内容）
├── pytest.ini
├── requirements.txt
└── README.md
```

---

## 三、怎么跑

**1. 启动被测服务**（已经在虚拟机里部署好）

```bash
# 虚拟机内
cd ~/realworld
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**2. 装依赖并运行**

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 默认连 http://192.168.251.135:8000/api
pytest -v

# 或指定地址
BASE_URL=http://localhost:8000/api pytest -v
```

**3. 常用筛选**

```bash
pytest -k "API-01"          # 只跑注册相关
pytest tests/test_smoke.py  # 只跑冒烟
pytest -k "not xfail"       # 看不到 xfail（pytest 没有这个语法，仅示意）
```

---

## 四、四个设计要点

### ① 用例与数据分离

101 条用例写在 `data/cases.csv` 里，测试代码只有 30 行：

```python
@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_case(case, api, base_url, ctx, ...):
    resp = send(case, ctx, api, base_url)
    assert resp.status_code in expected_codes(case)
```

**加一条用例 = 改 CSV，不改代码。**

### ② 数据参数化，解决"用例不能重跑"

每条用例里的用户名、邮箱、文章标题都会自动加上**本次运行的后缀**：

```
tester01  ->  tester01_a3f9c1
测试文章一 ->  测试文章一_a3f9c1
```

**同一个套件可以跑 100 遍，不会因为数据残留互相干扰。**

### ③ 夹具分层

```
session 级：user_a / user_b / article_a / comment_a   ← 只建一次
function 级：fresh_article                            ← 破坏性用例用
```

跑 109 个测试，只创建 4 次基础数据。

### ④ 已知问题用 xfail 登记，而不是删掉用例

```python
KNOWN_ISSUES = {
    "API-01-12": "BUG-RW-003 password 允许空字符串（且可登录）",
    "API-03-02": "S-01 无 token 返回 403（规范 401）",
    ...
}
```

- **用例本身是对的**，所以不删
- 实现修好后会变成 `XPASS`，提醒回来更新登记表

---

## 五、发现的缺陷

### 6 个真实缺陷

| 编号 | 问题 | 严重程度 |
|---|---|---|
| BUG-RW-001 | 密码 7 位即可注册 | 中 |
| BUG-RW-002 | username 允许空字符串，且错误提示误导 | 高 |
| BUG-RW-003 | password 允许空字符串，**且可登录** | 高 |
| BUG-RW-004 | 文章 title 允许空字符串 | 中 |
| BUG-RW-005 | 更新文章可把 title 置空 | 中 |
| BUG-RW-007 | 评论 body 允许空字符串 | 中 |

### 3 组系统性偏差

| 编号 | 现象 | 影响用例 |
|---|---|---|
| S-01 | 鉴权失败返回 **403**，规范要求 **401** | 16 条 |
| S-02 | 冲突/认证失败返回 **400**，规范要求 **409/401** | 6 条 |
| S-03 | 重复操作返回 **400**，规范期望幂等 | 3 条 |

**为什么系统性偏差更值得报告**：它不影响功能可用性，但会让**客户端的错误处理逻辑失效**
（无法判断该跳登录页还是提示无权限、无法区分格式错还是重名）。

---

## 六、执行过程中踩过的坑

| 现象 | 原因 | 解决 |
|---|---|---|
| 全部用例 404 | 用例路径 `/api/xxx` 与 BASE_URL 的 `/api` 重复 | 拼接前裁掉重复前缀 |
| 认证全部 403 | 用了 `Bearer` 前缀，该实现要求 `Token` | 改前缀（见 openapi.yml 的 securitySchemes）|
| 第二遍跑全挂 | 数据写死（tester01），跨轮冲突 | 加运行后缀 |
| 后面用例全 404 | 更新标题导致 slug 变化 | 更新后同步 slug |
| 评论用例 404 | 误把新建文章的 slug 当成共享文章 slug | 只对「更新文章」同步 slug |

> 完整的排查过程记录在 `../练习/day20/01_执行报告.md`。

---

## 七、简历可以这么写

> **RealWorld 开源项目 · 接口自动化测试**
> · 依据官方 OpenAPI 规范设计 **101 条**接口用例，覆盖 19 个接口，含正向、边界、鉴权、幂等、数据一致性
> · 用 pytest + requests 实现自动化，**数据参数化 + session 级夹具**，套件可重复执行
> · 发现 **6 个真实缺陷**（空值校验缺失、可空密码登录等）与 **3 组系统性错误码偏差**
> · 用 `xfail` 登记已知问题，实现修复后自动转为 XPASS 告警
