"""Notification throttling regression test."""
from gold_bot.notifiers import Notifier


def test_warning_accepts_throttle_arguments():
    n = Notifier([])
    n.warning("test", "body", throttle_key="x", throttle_seconds=60)
    n.warning("test", "body", throttle_key="x", throttle_seconds=60)
