"""业务冒烟测试：不只看状态码，还断言响应内容。

这是"状态码通过 ≠ 功能正确"的补位。
"""

import uuid

import pytest

from case_engine import Ctx, expected_codes


def _auth(token):
    return {"Authorization": f"Token {token}"}


def test_注册返回token且不回传密码(api, base_url, ctx):
    uname = f"smoke_{uuid.uuid4().hex[:6]}"
    r = api.post(f"{base_url}/users",
                 json={"user": {"username": uname, "email": f"{uname}@test.com",
                                "password": "12345678"}}, timeout=10)
    assert r.status_code == 201, r.text
    body = r.json()["user"]
    assert body["username"] == uname
    assert body["token"], "注册必须返回 token"
    assert "password" not in body, "响应里不能出现密码字段"


def test_登录返回的token可以访问_当前用户(api, base_url, user_a):
    r = api.post(f"{base_url}/users/login",
                 json={"user": {"email": user_a["email"], "password": "12345678"}}, timeout=10)
    assert r.status_code == 200, r.text
    token = r.json()["user"]["token"]

    me = api.get(f"{base_url}/user", headers=_auth(token), timeout=10)
    assert me.status_code == 200, me.text
    assert me.json()["user"]["username"] == user_a["username"]


def test_创建文章后能通过详情接口读到(api, base_url, user_a, ctx):
    title = f"链路验证 {uuid.uuid4().hex[:6]}"
    c = api.post(f"{base_url}/articles",
                 json={"article": {"title": title, "description": "d",
                                   "body": "b", "tagList": ["test"]}},
                 headers=_auth(user_a["token"]), timeout=10)
    assert c.status_code == 201, c.text
    slug = c.json()["article"]["slug"]

    g = api.get(f"{base_url}/articles/{slug}", timeout=10)
    assert g.status_code == 200, g.text
    assert g.json()["article"]["title"] == title
    assert g.json()["article"]["author"]["username"] == user_a["username"]


def test_评论后文章详情的评论列表变长(api, base_url, user_a):
    uname = f"cmt_{uuid.uuid4().hex[:6]}"
    a = api.post(f"{base_url}/articles",
                 json={"article": {"title": uname, "description": "d",
                                   "body": "b", "tagList": []}},
                 headers=_auth(user_a["token"]), timeout=10)
    slug = a.json()["article"]["slug"]

    before = api.get(f"{base_url}/articles/{slug}/comments", timeout=10).json()["comments"]
    api.post(f"{base_url}/articles/{slug}/comments",
             json={"comment": {"body": "新评论"}},
             headers=_auth(user_a["token"]), timeout=10)
    after = api.get(f"{base_url}/articles/{slug}/comments", timeout=10).json()["comments"]

    assert len(after) == len(before) + 1, "评论数没有变化，写入可能没生效"


def test_收藏后favorited为true且计数加一(api, base_url, user_a):
    uname = f"fav_{uuid.uuid4().hex[:6]}"
    a = api.post(f"{base_url}/articles",
                 json={"article": {"title": uname, "description": "d",
                                   "body": "b", "tagList": []}},
                 headers=_auth(user_a["token"]), timeout=10)
    slug = a.json()["article"]["slug"]

    before = api.get(f"{base_url}/articles/{slug}", timeout=10).json()["article"]["favoritesCount"]
    r = api.post(f"{base_url}/articles/{slug}/favorite",
                 headers=_auth(user_a["token"]), timeout=10)
    assert r.status_code == 200, r.text

    after = api.get(f"{base_url}/articles/{slug}",
                    headers=_auth(user_a["token"]), timeout=10).json()["article"]
    assert after["favorited"] is True
    assert after["favoritesCount"] == before + 1, "收藏数没有加一"


def test_按tag筛选的结果都带该标签(api, base_url, article_a):
    r = api.get(f"{base_url}/articles", params={"tag": "docker", "limit": 20}, timeout=10)
    assert r.status_code == 200, r.text
    for art in r.json()["articles"]:
        assert "docker" in art["tagList"], f"{art['slug']} 不含 docker 标签"
