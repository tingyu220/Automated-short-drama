"""验证所有包模块可正常导入."""


def test_import_backend():
    """验证 backend 包的顶层导入."""
    import backend  # noqa: F811
    assert backend is not None


def test_import_domain():
    """验证 domain 子包导入."""
    from backend import domain  # noqa: F811
    assert domain is not None


def test_import_application():
    """验证 application 子包导入."""
    from backend import application  # noqa: F811
    assert application is not None


def test_import_platforms():
    """验证 platforms 子包导入."""
    from backend import platforms  # noqa: F811
    assert platforms is not None


def test_import_infrastructure():
    """验证 infrastructure 子包导入."""
    from backend import infrastructure  # noqa: F811
    assert infrastructure is not None


def test_import_interfaces():
    """验证 interfaces 子包导入."""
    from backend import interfaces  # noqa: F811
    assert interfaces is not None


def test_import_bootstrap():
    """验证 bootstrap 子包导入."""
    from backend import bootstrap  # noqa: F811
    assert bootstrap is not None
