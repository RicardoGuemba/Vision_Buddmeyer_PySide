# -*- coding: utf-8 -*-
"""Testes dos novos TAGs de segmentação (CentroidAngle, ObjectArea)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestTagMapSegmentation:
    def test_centroid_angle_defined(self):
        from communication.tag_map import TagMap, TagType, TagDirection

        defn = TagMap.DEFINITIONS.get("CentroidAngle")
        assert defn is not None
        assert defn.tag_type == TagType.REAL
        assert defn.direction == TagDirection.WRITE
        assert defn.plc_name

    def test_object_area_defined(self):
        from communication.tag_map import TagMap, TagType, TagDirection

        defn = TagMap.DEFINITIONS.get("ObjectArea")
        assert defn is not None
        assert defn.tag_type == TagType.REAL
        assert defn.direction == TagDirection.WRITE

    def test_map_returns_plc_names(self):
        from communication.tag_map import TagMap

        tm = TagMap()
        assert tm.is_valid_tag("CentroidAngle")
        assert tm.is_valid_tag("ObjectArea")
        assert tm.is_writable("CentroidAngle")
        assert tm.is_writable("ObjectArea")

    def test_real_values_accepted(self):
        from communication.tag_map import TagMap

        tm = TagMap()
        assert tm.validate_value("CentroidAngle", 45.0) is True
        assert tm.validate_value("CentroidAngle", 0) is True
        assert tm.validate_value("ObjectArea", 1234.56) is True
