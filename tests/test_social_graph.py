from __future__ import annotations

import unittest

from abm.model.daily import StudentDailyModel


class SocialGraphSnapshotTest(unittest.TestCase):
    def test_only_friend_or_intimate_pairs_are_drawn_and_mutual_pairs_are_marked(self) -> None:
        model = StudentDailyModel(
            "map/summary.json",
            student_count=5,
            start_time="07:30:00",
            seconds_per_step=300,
            rng=5,
        )
        model.outer_mind.set_relationship(1, 2, closeness=0.30)
        model.outer_mind.set_relationship(2, 1, closeness=0.20)
        model.outer_mind.set_relationship(1, 3, closeness=0.80)
        model.outer_mind.set_relationship(3, 1, closeness=0.35)
        model.outer_mind.set_relationship(1, 4, closeness=0.80)
        model.outer_mind.set_relationship(4, 1, closeness=0.75)
        model.outer_mind.set_relationship(2, 4, closeness=0.40)
        model.outer_mind.set_relationship(4, 2, closeness=0.30)
        model.outer_mind.set_relationship(2, 3, closeness=0.29)
        model.outer_mind.set_relationship(3, 2, closeness=0.29)

        graph = model.social_graph_snapshot()

        self.assertEqual(
            graph["ties"],
            [
                {"source": 1, "target": 2, "closeness": 0.30, "tier": "friend", "mutual": False},
                {"source": 1, "target": 3, "closeness": 0.80, "tier": "intimate", "mutual": False},
                {"source": 1, "target": 4, "closeness": 0.80, "tier": "intimate", "mutual": True},
                {"source": 2, "target": 4, "closeness": 0.40, "tier": "friend", "mutual": True},
            ],
        )
        self.assertEqual([node["id"] for node in graph["nodes"]], [1, 2, 3, 4])


if __name__ == "__main__":
    unittest.main()
