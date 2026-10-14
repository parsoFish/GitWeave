"""Smoke-test: verify gitweave.self_serve is fully importable and wired."""


def test_self_serve_package_importable():
    from gitweave.self_serve import new_repo, update_content, membership, exceptions  # noqa: F401

    assert hasattr(new_repo, "self_serve_new_repo")
    assert hasattr(update_content, "self_serve_update_content")
    assert hasattr(membership, "self_serve_add_member")
    assert hasattr(exceptions, "self_serve_add_exception")


def test_policy_and_auth_importable():
    from gitweave.policy import PolicyLoader, PolicyDenied  # noqa: F401
    from gitweave.auth import get_caller_token, CallerTokenRequiredError  # noqa: F401

    assert callable(PolicyLoader)
    assert callable(get_caller_token)
