def test_import_gui_package():
    import importlib

    module = importlib.import_module("jp2subs.gui")
    assert module is not None

