"""验证所有包模块可正常导入."""


def test_import_backend():
    """验证 backend 包的顶层导入."""
    import backend
    assert backend is not None


def test_import_domain():
    """验证 domain 子包导入."""
    from backend import domain
    assert domain is not None


def test_import_application():
    """验证 application 子包导入."""
    from backend import application
    assert application is not None


def test_import_platforms():
    """验证 platforms 子包导入."""
    from backend import platforms
    assert platforms is not None


def test_import_infrastructure():
    """验证 infrastructure 子包导入."""
    from backend import infrastructure
    assert infrastructure is not None


def test_import_interfaces():
    """验证 interfaces 子包导入."""
    from backend import interfaces
    assert interfaces is not None


def test_import_bootstrap():
    """验证 bootstrap 子包导入."""
    from backend import bootstrap
    assert bootstrap is not None
