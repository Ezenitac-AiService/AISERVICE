from deployment.nginx.switch_upstream import (
    ACTIVE_CONF,
    CANDIDATE_CONF,
    ROLLBACK_CONF,
    check_nginx_syntax,
    get_current_status,
    switch_upstream_atomic,
)


def test_nginx_syntax_check():
    assert check_nginx_syntax(CANDIDATE_CONF) is True
    assert check_nginx_syntax(ROLLBACK_CONF) is True


def test_switch_upstream_apply_and_rollback():
    # 1. Apply Green candidate
    res_apply = switch_upstream_atomic("candidate")
    assert res_apply["status"] == "APPLIED"
    assert res_apply["active_target"] == "GREEN_UNIFIED"
    assert get_current_status() == "GREEN_CANDIDATE"
    assert "15050" in ACTIVE_CONF.read_text(encoding="utf-8")

    # 2. Rollback to Blue legacy
    res_rollback = switch_upstream_atomic("rollback")
    assert res_rollback["status"] == "APPLIED"
    assert res_rollback["active_target"] == "BLUE_LEGACY"
    assert get_current_status() == "BLUE_ROLLBACK"
    assert "5050" in ACTIVE_CONF.read_text(encoding="utf-8")
