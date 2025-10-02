from src.llm_query_doc_analyser.filter_rank.rules import rule_filter


def test_rule_filter_positive():
    keep, _, reasons = rule_filter("semantic segmentation of 2d images")
    assert keep
    assert any("include" in r for r in reasons)


def test_rule_filter_negative():
    keep, _, reasons = rule_filter("3d volumetric point cloud")
    assert not keep
    assert any("exclude" in r for r in reasons)
