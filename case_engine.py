"""用例引擎：把 CSV 里的一行用例变成一次真实的 HTTP 请求。

设计要点
--------
1. **数据参数化**：每次运行生成唯一后缀，所有用户名/邮箱/标题都带后缀，
   所以整套用例可以反复跑，不会互相冲突。
2. **解析与执行分离**：这里只负责"读用例 -> 发请求"，断言在测试里。
3. **失败要能看得懂**：请求和响应的关键信息都会带进断言消息。
"""

import csv
import json
import re
import uuid
from pathlib import Path

import requests

HERE = Path(__file__).parent
CASES_FILE = HERE / "data" / "cases.csv"

# 有副作用的用例（删除/改资料/改名），放到单独模块里跑，避免污染主套件
DESTRUCTIVE = {
    # 改资料 / 删除 / 改文章：都会改变共享数据的状态
    "API-04-01", "API-04-02", "API-04-06",
    "API-12-01", "API-12-05", "API-12-06",
    "API-13-01", "API-13-04", "API-13-05", "API-16-01",
}

DESTRUCTIVE_ORDER = {
    "API-13-01": 1, "API-13-04": 1, "API-13-05": 1, "API-16-01": 1,
    "API-04-01": 2, "API-04-02": 2,
    "API-04-06": 3,
}


def new_run_id():
    """每次运行一个后缀，保证数据唯一。"""
    return uuid.uuid4().hex[:6]


def load_cases(path=CASES_FILE, include_destructive=False):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if include_destructive:
        rows.sort(key=lambda r: DESTRUCTIVE_ORDER.get(r["用例编号"], 0))
    else:
        rows = [r for r in rows if r["用例编号"] not in DESTRUCTIVE]
    return rows


def expected_codes(case):
    """解析「预期状态码」列，支持 200 / 200 或 422 两种写法。"""
    raw = (case.get("预期状态码") or "").strip()
    if "或" in raw:
        return [int(x) for x in re.findall(r"\d{3}", raw)]
    try:
        return [int(raw)]
    except ValueError:
        return []


class Ctx:
    """一次运行内的共享上下文。"""

    def __init__(self, run_id=None):
        self.run_id = run_id or new_run_id()
        self.token_a = None
        self.token_b = None
        self.slug = None
        self.comment_id = None

    # ---------- 数据替换 ----------
    def sub(self, text):
        if not text:
            return text
        text = text.replace("tester01", f"tester01_{self.run_id}")
        text = text.replace("tester02", f"tester02_{self.run_id}")
        text = text.replace("{user_a}", f"tester01_{self.run_id}")
        text = text.replace("{user_b}", f"tester02_{self.run_id}")
        text = text.replace("{token_a}", self.token_a or "")
        text = text.replace("{token_b}", self.token_b or "")
        text = text.replace("{token}", self.token_a or "")
        if self.slug:
            text = text.replace("{slug}", self.slug)
        if self.comment_id:
            text = text.replace("{id}", str(self.comment_id))
        return text

    def suffix_json(self, obj):
        """给 username / email / title 加唯一后缀（空值不动）。"""
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str):
                    if k == "username" and v.strip():
                        obj[k] = v if v.endswith(f"_{self.run_id}") else f"{v}_{self.run_id}"
                    elif k == "email" and "@" in v:
                        local, dom = v.split("@", 1)
                        obj[k] = v if local.endswith(f"_{self.run_id}") else f"{local}_{self.run_id}@{dom}"
                    elif k == "title" and v.strip():
                        obj[k] = v if v.endswith(f"_{self.run_id}") else f"{v}_{self.run_id}"
                else:
                    self.suffix_json(v)
        elif isinstance(obj, list):
            for it in obj:
                self.suffix_json(it)


def parse_body(case, ctx):
    raw = case.get("请求体") or ""
    if not raw.strip() or raw.strip() == "无":
        return None
    text = ctx.sub(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text          # 故意发非法 JSON 的用例
    ctx.suffix_json(data)
    return data


def parse_headers(case, ctx, use_other=False):
    raw = case.get("请求头") or ""
    if not raw.strip() or raw.strip() == "无":
        return {}
    if use_other and ctx.token_b:
        raw = raw.replace("{token}", ctx.token_b)
    headers = {}
    for line in ctx.sub(raw).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip()] = v.strip()
    return headers


def send(case, ctx, api, base_url):
    """按用例发一次请求，返回 Response。"""
    method = (case.get("方法") or "GET").upper()
    path = ctx.sub(case.get("路径") or "/")
    title = case.get("用例标题") or ""
    use_other = ("别人" in title) or ("越权" in title)

    # 用例表里的路径是 /api/xxx 完整路径，而 base_url 已经带 /api，
    # 直接拼会变成 /api/api/xxx -> 404
    if base_url.endswith("/api") and path.startswith("/api/"):
        path = path[len("/api"):]

    headers = parse_headers(case, ctx, use_other)
    body = parse_body(case, ctx)

    return api.request(
        method,
        f"{base_url}{path}",
        headers=headers,
        json=body if isinstance(body, dict) else None,
        data=body if isinstance(body, str) else None,
        timeout=15,
    )


def describe(case, resp):
    """断言失败时打印的信息。"""
    return (
        f"\n用例 {case['用例编号']}：{case['用例标题']}"
        f"\n  {case.get('方法')} {case.get('路径')}"
        f"\n  请求体: {case.get('请求体')}"
        f"\n  预期状态码: {case.get('预期状态码')}"
        f"\n  实际状态码: {resp.status_code}"
        f"\n  实际响应: {resp.text[:300]}"
    )
