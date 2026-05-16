import os
import sys
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app import crud
from app.models import Base, Inscription


class TimelineSortingTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        Session = sessionmaker(bind=self.engine)
        self.db = Session()

    def tearDown(self):
        self.db.close()

    def add_inscription(self, serial_num, name, era):
        self.db.add(Inscription(serial_num=serial_num, name=name, era=era))

    def test_extract_year_num_supports_common_era_formats(self):
        cases = {
            "乾亨三年（公元981年）": 981,
            "統合二十九年（西元1011年）": 1011,
            "天祚間（公元1101-1125年）": 1101,
            "保寧間（公元969年至979年）": 969,
        }
        for era, expected in cases.items():
            with self.subTest(era=era):
                self.assertEqual(crud.extract_year_num(era), expected)

        self.assertEqual(crud.extract_year_num("未詳"), crud.UNKNOWN_YEAR_SORT)

    def test_timeline_groups_are_sorted_by_chronological_year(self):
        self.add_inscription("[004]", "未详墓志", "未詳")
        self.add_inscription("[003]", "天祚墓志", "天祚間（公元1101-1125年）")
        self.add_inscription("[001]", "乾亨墓志", "乾亨三年（公元981年）")
        self.add_inscription("[002]", "保宁墓志", "保寧元年（公元969年）")
        self.db.commit()

        result = crud.get_timeline_data(self.db, include_all=True)

        self.assertEqual(
            [era["name"] for era in result["eras"]],
            ["保寧", "乾亨", "天祚", "未詳"],
        )

    def test_samples_inside_era_group_are_sorted_by_year_then_serial(self):
        self.add_inscription("[003]", "大康三", "大康三年（公元1077年）")
        self.add_inscription("[002]", "大康二乙", "大康二年（公元1076年）")
        self.add_inscription("[001]", "大康二甲", "大康二年（公元1076年）")
        self.db.commit()

        result = crud.get_timeline_data(self.db, include_all=True)
        samples = result["eras"][0]["samples"]

        self.assertEqual(
            [item["serial_num"] for item in samples],
            ["[001]", "[002]", "[003]"],
        )


if __name__ == "__main__":
    unittest.main()
