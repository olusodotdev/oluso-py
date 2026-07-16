import threading

from oluso import add_breadcrumb, scope, set_custom_context, set_user
from oluso.context import _snapshot
from oluso.types import UserContext


def test_add_breadcrumb_and_snapshot():
    with scope():
        add_breadcrumb("step 1")
        add_breadcrumb("step 2")
        set_user(UserContext(id="user-1"))
        set_custom_context("cartId", "cart-42")

        breadcrumbs, user, custom = _snapshot()

        assert [b.message for b in breadcrumbs] == ["step 1", "step 2"]
        assert user.id == "user-1"
        assert custom["cartId"] == "cart-42"


def test_max_breadcrumbs_evicts_oldest():
    with scope(max_breadcrumbs=2):
        add_breadcrumb("1")
        add_breadcrumb("2")
        add_breadcrumb("3")

        breadcrumbs, _, _ = _snapshot()
        assert [b.message for b in breadcrumbs] == ["2", "3"]


def test_no_op_outside_scope():
    # None of these should raise even though there's no active scope.
    add_breadcrumb("ignored")
    set_user(UserContext(id="ignored"))
    set_custom_context("k", "v")

    breadcrumbs, user, custom = _snapshot()
    assert breadcrumbs == []
    assert user is None
    assert custom == {}


def test_scope_resets_after_exit():
    with scope():
        add_breadcrumb("inside")
    breadcrumbs, _, _ = _snapshot()
    assert breadcrumbs == []


def test_scopes_are_isolated_across_threads():
    results = {}

    def worker(name, message):
        with scope():
            add_breadcrumb(message)
            breadcrumbs, _, _ = _snapshot()
            results[name] = [b.message for b in breadcrumbs]

    t1 = threading.Thread(target=worker, args=("t1", "only in t1"))
    t2 = threading.Thread(target=worker, args=("t2", "only in t2"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results["t1"] == ["only in t1"]
    assert results["t2"] == ["only in t2"]
