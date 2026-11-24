"""数据驱动的主测试套件。

每一条用例来自 data/cases.csv（101 条，19 个接口）。
已知问题用 xfail 标记，原因见 known_issues.py。

运行：
    pytest -v
    pytest -v -k "API-01"           # 只跑注册相关
    BASE_URL=http://其他地址/api pytest -v
"""

import pytest

import known_issues
from case_engine import describe, expected_codes, load_cases, send

CASES = load_cases(include_destructive=False)
IDS = [c["用例编号"] for c in CASES]


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_case(case, api, base_url, ctx, user_a, user_b, article_a, article_b, comment_a):
    """按用例表执行一条接口用例，断言状态码。"""
    expected = expected_codes(case)
    assert expected, f"用例 {case['用例编号']} 的预期状态码无法解析：{case.get('预期状态码')!r}"

    reason = known_issues.reason(case["用例编号"])
    resp = send(case, ctx, api, base_url)

    # 只有「更新文章」会改变已有文章的 slug，后面用 {slug} 的用例需要同步。
    # 注意不能对所有返回 article.slug 的响应都同步——新建文章也会返回 slug，
    # 那样会把 ctx.slug 指到新文章上，后面的评论/收藏用例就 404 了。
    is_article_update = (
        (case.get("方法") or "").upper() == "PUT"
        and "{slug}" in (case.get("路径") or "")
    )
    if is_article_update:
        try:
            new_slug = resp.json().get("article", {}).get("slug")
            if new_slug:
                ctx.slug = new_slug
        except (ValueError, AttributeError):
            pass

    if reason:
        pytest.xfail(f"{reason}｜实际 {resp.status_code}")
        return

    assert resp.status_code in expected, describe(case, resp)
