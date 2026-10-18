import pytest
from vorqeli_connect.module_registry import MODULES, get_module

def test_known_modules():
    assert {m.kind.value for m in MODULES} == {"dpi", "telegram"}

def test_support_descriptions_are_explicit():
    assert all(m.supported for m in MODULES)
    assert "Эксперименталь" in get_module("dpi").detail
    assert "Python" in get_module("telegram").detail

def test_unknown_module():
    with pytest.raises(ValueError):
        get_module("unknown")
