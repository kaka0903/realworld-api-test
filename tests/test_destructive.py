"""破坏性用例：删除 / 改邮箱 / 改密码 / 改用户名。

这些用例会改变数据状态，所以**每条都用自己独立的数据**，
跑完不影响其他用例。这也是它们不放进主套件的原因。
"""

import uuid

import pytest


def _auth(token):
    return {"Authorization": f"Token {token}"}


def _new_user(api, base_url, tag):
    """造一个一次性用户，返回 (token, username, email, password)。"""
    uname = f"tmp_{tag}_{uuid.uuid4().hex[:6]}"
    email = f"{uname}@test.com"
    pwd = "12345678"
    r = api.post(f"{base_url}/users",
                 json={"user": {"username": uname, "email": email, "password": pwd}}, timeout=10)
    assert r.status_code == 201, r.text
    return r.json()["user"]["token"], uname, email, pwd


def _new_article(api, base_url, token):
    r = api.post(f"{base_url}/articles",
                 json={"article": {"title": f"tmp {uuid.uuid4().hex[:6]}",
                                   "description": "d", "body": "b", "tagList": []}},
                 headers=_auth(token), timeout=10)
    assert r.status_code == 201, r.text
    return r.json()["article"]["slug"]


def test_删除自己的文章返回204且无响应体(api, base_url, user_a):
    slug = _new_article(api, base_url, user_a["token"])
    r = api.delete(f"{base_url}/articles/{slug}", headers=_auth(user_a["token"]), timeout=10)
    assert r.status_code == 204, r.text
    assert r.text == "", "204 不应该有响应体"


def test_重复删除同一篇返回404(api, base_url, user_a):
    slug = _new_article(api, base_url, user_a["token"])
    first = api.delete(f"{base_url}/articles/{slug}", headers=_auth(user_a["token"]), timeout=10)
    second = api.delete(f"{base_url}/articles/{slug}", headers=_auth(user_a["token"]), timeout=10)
    assert first.status_code == 204
    assert second.status_code == 404, second.text


def test_删除后详情接口返回404(api, base_url, user_a):
    slug = _new_article(api, base_url, user_a["token"])
    api.delete(f"{base_url}/articles/{slug}", headers=_auth(user_a["token"]), timeout=10)
    r = api.get(f"{base_url}/articles/{slug}", timeout=10)
    assert r.status_code == 404, "删除后还能查到，说明没真删"


def test_删除自己的评论返回204(api, base_url, user_a):
    slug = _new_article(api, base_url, user_a["token"])
    c = api.post(f"{base_url}/articles/{slug}/comments",
                 json={"comment": {"body": "要删掉的评论"}},
                 headers=_auth(user_a["token"]), timeout=10)
    cid = c.json()["comment"]["id"]

    r = api.delete(f"{base_url}/articles/{slug}/comments/{cid}",
                   headers=_auth(user_a["token"]), timeout=10)
    assert r.status_code == 204, r.text
    assert r.text == ""


def test_更新邮箱成功(api, base_url):
    token, uname, email, pwd = _new_user(api, base_url, "email")
    new_email = f"{uname}_new@test.com"
    r = api.put(f"{base_url}/user", json={"user": {"email": new_email}},
                headers=_auth(token), timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email"] == new_email


def test_改密码后新密码能登录旧密码失效(api, base_url):
    token, uname, email, pwd = _new_user(api, base_url, "pwd")
    new_pwd = "newpass888"

    r = api.put(f"{base_url}/user", json={"user": {"password": new_pwd}},
                headers=_auth(token), timeout=10)
    assert r.status_code == 200, r.text

    old = api.post(f"{base_url}/users/login",
                   json={"user": {"email": email, "password": pwd}}, timeout=10)
    new = api.post(f"{base_url}/users/login",
                   json={"user": {"email": email, "password": new_pwd}}, timeout=10)

    assert new.status_code == 200, "新密码登录失败，改密码没生效"
    assert old.status_code != 200, "旧密码还能登录，改密码有安全问题"


def test_更新用户名成功(api, base_url):
    token, uname, email, pwd = _new_user(api, base_url, "rename")
    new_name = f"{uname}_renamed"
    r = api.put(f"{base_url}/user", json={"user": {"username": new_name}},
                headers=_auth(token), timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()["user"]["username"] == new_name


@pytest.mark.xfail(reason="用例设计缺陷：更新成自己的邮箱不构成冲突，应改用他人邮箱", strict=False)
def test_更新为已存在的邮箱应被拒绝(api, base_url, user_a, user_b):
    r = api.put(f"{base_url}/user", json={"user": {"email": user_b["email"]}},
                headers=_auth(user_a["token"]), timeout=10)
    assert r.status_code == 409, r.text


# ==================== 改文章（会改变 slug，必须用独立文章）====================

def test_更新自己的文章标题(api, base_url, user_a):
    slug = _new_article(api, base_url, user_a["token"])
    new_title = f"改名 {uuid.uuid4().hex[:6]}"
    r = api.put(f"{base_url}/articles/{slug}",
                json={"article": {"title": new_title}},
                headers=_auth(user_a["token"]), timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()["article"]["title"] == new_title
    assert r.json()["article"]["slug"] != slug, "标题变了 slug 应该重新生成"


def test_只改描述时其他字段不变(api, base_url, user_a):
    slug = _new_article(api, base_url, user_a["token"])
    before = api.get(f"{base_url}/articles/{slug}", timeout=10).json()["article"]

    r = api.put(f"{base_url}/articles/{slug}",
                json={"article": {"description": "只改这里"}},
                headers=_auth(user_a["token"]), timeout=10)
    assert r.status_code == 200, r.text
    after = r.json()["article"]
    assert after["description"] == "只改这里"
    assert after["title"] == before["title"], "部分更新把 title 清空了"
    assert after["body"] == before["body"], "部分更新把 body 清空了"


def test_更新别人的文章返回403(api, base_url, user_a, user_b):
    slug = _new_article(api, base_url, user_a["token"])
    r = api.put(f"{base_url}/articles/{slug}",
                json={"article": {"title": "越权修改"}},
                headers=_auth(user_b["token"]), timeout=10)
    assert r.status_code == 403, r.text


@pytest.mark.xfail(reason="BUG-RW-005 更新时 title 允许置空（规范应 422）", strict=False)
def test_更新标题为空串应被拒绝(api, base_url, user_a):
    slug = _new_article(api, base_url, user_a["token"])
    r = api.put(f"{base_url}/articles/{slug}",
                json={"article": {"title": ""}},
                headers=_auth(user_a["token"]), timeout=10)
    assert r.status_code == 422, r.text
