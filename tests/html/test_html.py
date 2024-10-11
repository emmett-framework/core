import pytest

from emmett_core.html import MetaHtmlTag, TagStack, TreeHtmlTag, cat


@pytest.fixture(scope="module")
def tag():
    stack = TagStack()
    return MetaHtmlTag(stack)


@pytest.fixture(scope="module")
def ttag():
    class MetaTreeHtmlTag(MetaHtmlTag):
        _tag_cls = TreeHtmlTag

    stack = TagStack()
    return MetaTreeHtmlTag(stack)


def test_tag_self_closed(tag):
    br = tag.br()
    assert str(br) == "<br />"


def test_tag_non_closed(tag):
    p = tag.p()
    assert str(p) == "<p></p>"


def test_tag_components(tag):
    t = tag.div(tag.p(), tag.p())
    assert str(t) == "<div><p></p><p></p></div>"


def test_tag_attributes(tag):
    d = tag.div(_class="test", _id="test", _test="test")
    assert str(d) == '<div class="test" id="test" test="test"></div>'


def test_tag_attributes_dict(tag):
    d = tag.div(_class="test", _hx={"foo": "bar"})
    assert str(d) == '<div class="test" hx-foo="bar"></div>'


def test_tag_attributes_data(tag):
    d = tag.div(_data={"foo": "bar"})
    assert str(d) == '<div data-foo="bar"></div>'


def test_cat(tag):
    t = cat(tag.p(), tag.p())
    assert str(t) == "<p></p><p></p>"


def test_tag_stack(tag):
    t = tag.div(_class="l0")
    with t:
        with tag.div(_class="l1"):
            tag.p("t1")
            with tag.p() as p:
                p.append("t2")
        with tag.div(_class="l1"):
            tag.p("t3")
    assert str(t) == '<div class="l0"><div class="l1"><p>t1</p><p>t2</p></div><div class="l1"><p>t3</p></div></div>'


def test_tag_tree_stack(ttag):
    t = ttag.div(_class="l0")
    with t:
        with ttag.div(_class="l1") as d1:
            assert d1.parent is t
            p1 = ttag.p("t1")
            assert p1.parent is d1
            with ttag.p() as p2:
                assert p2.parent is d1
                p2.append("t2")
        with ttag.div(_class="l1") as d2:
            assert d2.parent is t
            p3 = ttag.p("t3")
            assert p3.parent is d2
    assert str(t) == '<div class="l0"><div class="l1"><p>t1</p><p>t2</p></div><div class="l1"><p>t3</p></div></div>'
