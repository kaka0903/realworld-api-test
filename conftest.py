"""pytest 夹具：一次运行准备一次数据，所有用例共享。

设计要点
--------
1. **session 级夹具**：用户、文章、评论只创建一次，避免 100 条用例造 100 次数据
2. **数据唯一**：用 run_id 后缀，重复运行不冲突
3. **服务探活**：服务没起时给一句人话，而不是 90 个 ConnectionError
"""

import os

import pytest
import requests

import case_engine
from case_engine import Ctx

BASE_URL = os.environ.get("BASE_URL", "http://192.168.251.135:8000/api").rstrip("/")
PASSWORD = "12345678"


def _auth(token):
    return {"Authorization": f"Token {token}"}


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session", autouse=True)
def server_alive(base_url):
    """服务没起就早点退出，给一句人话。"""
    try:
        r = requests.get(f"{base_url}/tags", timeout=5)
    except requests.RequestException as e:
        pytest.exit(
            f"\n连不上被测服务：{base_url}"
            f"\n请先在虚拟机里启动服务，再设置环境变量 BASE_URL"
            f"\n原始错误：{type(e).__name__}: {e}",
            returncode=1,
        )
    assert r.status_code == 200, f"服务异常，GET /tags 返回 {r.status_code}"


@pytest.fixture(scope="session")
def api():
    """整个会话复用一个 Session（连接复用 + 统一 header）。"""
    with requests.Session() as s:
        s.headers.update({"Content-Type": "application/json"})
        yield s


@pytest.fixture(scope="session")
def ctx():
    return Ctx()


def _register_or_login(api, base_url, username, password=PASSWORD):
    """注册；已存在就登录。返回 (token, email)。"""
    email = f"{username}@test.com"
    r = api.post(f"{base_url}/users",
                 json={"user": {"username": username, "email": email, "password": password}},
                 timeout=10)
    if r.status_code in (400, 409, 422):
        r = api.post(f"{base_url}/users/login",
                     json={"user": {"email": email, "password": password}}, timeout=10)
    assert r.status_code in (200, 201), f"准备用户 {username} 失败：{r.status_code} {r.text}"
    return r.json()["user"]["token"], email


@pytest.fixture(scope="session")
def user_a(api, base_url, ctx):
    username = f"fx_a_{ctx.run_id}"
    token, email = _register_or_login(api, base_url, username)
    ctx.token_a = token
    return {"username": username, "email": email, "token": token}


@pytest.fixture(scope="session")
def user_b(api, base_url, ctx, user_a):
    username = f"tester02_{ctx.run_id}"   # 用例里写死了 tester02
    token, email = _register_or_login(api, base_url, username)
    ctx.token_b = token
    return {"username": username, "email": email, "token": token}


def _create_article(api, base_url, token, title, tags):
    r = api.post(f"{base_url}/articles",
                 json={"article": {"title": title, "description": "fixture",
                                   "body": "fixture body", "tagList": tags}},
                 headers=_auth(token), timeout=10)
    assert r.status_code == 201, f"准备文章失败：{r.status_code} {r.text}"
    return r.json()["article"]["slug"]


@pytest.fixture(scope="session")
def article_a(api, base_url, ctx, user_a):
    """tester01 的文章，供详情/评论/收藏类用例使用。"""
    slug = _create_article(api, base_url, user_a["token"],
                           f"fx 文章A {ctx.run_id}", ["docker", "test"])
    ctx.slug = slug
    return slug


@pytest.fixture(scope="session")
def article_b(api, base_url, ctx, user_b):
    """tester02 的文章，供 feed 用例使用。"""
    return _create_article(api, base_url, user_b["token"],
                           f"fx 文章B {ctx.run_id}", ["test"])


@pytest.fixture(scope="session")
def comment_a(api, base_url, ctx, user_a, article_a):
    r = api.post(f"{base_url}/articles/{article_a}/comments",
                 json={"comment": {"body": f"fx 评论 {ctx.run_id}"}},
                 headers=_auth(user_a["token"]), timeout=10)
    assert r.status_code == 201, f"准备评论失败：{r.status_code} {r.text}"
    ctx.comment_id = r.json()["comment"]["id"]
    return ctx.comment_id


@pytest.fixture()
def fresh_article(api, base_url, user_a, ctx):
    """函数级：每条破坏性用例用自己的一篇文章，互不影响。"""
    slug = _create_article(api, base_url, user_a["token"],
                           f"tmp 文章 {ctx.run_id}-{case_engine.uuid.uuid4().hex[:4]}", ["test"])
    return slug
