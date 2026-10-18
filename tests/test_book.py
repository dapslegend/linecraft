import json
import unittest
from unittest.mock import patch

from linecraft.book import BookError, assert_share_only, share_sporty
from linecraft.config import load_config
from linecraft.feeds import pull_games
from linecraft.__main__ import selections_from_keeps


class BookTests(unittest.TestCase):
    def test_config_refuses_a_stake(self) -> None:
        with self.assertRaises(ValueError):
            with patch("linecraft.config.Path.exists", return_value=True), patch(
                "linecraft.config.Path.read_text",
                return_value=json.dumps({"book": {"stake": True, "mode": "share"}}),
            ):
                load_config("config.example.json")

    def test_default_config_is_share_only_and_grok_on(self) -> None:
        config = load_config(None)
        self.assertEqual(config["provider"], "sporty")
        self.assertTrue(config["grok"]["enabled"])
        self.assertEqual(config["grok"]["model"], "grok-4.7")
        self.assertFalse(config["book"]["stake"])
        assert_share_only(config)

    def test_share_payload_has_string_odds_and_no_stake(self) -> None:
        captured = {}

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"bizCode": 10000, "data": {"shareCode": "TEST01"}}).encode()

        def fake_urlopen(req, timeout=0):
            captured["body"] = json.loads(req.data.decode())
            captured["url"] = req.full_url
            return FakeResp()

        with patch("linecraft.book.urllib.request.urlopen", fake_urlopen):
            result = share_sporty(
                [{
                    "eventId": "sr:match:1",
                    "marketId": "18",
                    "specifier": "total=2.5",
                    "outcomeId": "12",
                    "odds": 1.9,
                }]
            )
        self.assertEqual(result["data"]["shareCode"], "TEST01")
        selection = captured["body"]["selections"][0]
        self.assertEqual(selection["odds"], "1.90")
        self.assertNotIn("stake", captured["body"])
        self.assertNotIn("stake", selection)
        self.assertIn("/orders/share", captured["url"])

    def test_unknown_provider_is_refused(self) -> None:
        with self.assertRaises(Exception):
            pull_games({"provider": "stake-now", "sports": []})

    def test_research_without_outcome_id_is_not_booked(self) -> None:
        ready = selections_from_keeps([{"eventId": "1", "selection": "Home", "fact": "x" * 50}])
        self.assertEqual(ready, [])

    def test_assert_share_only_rejects_bet_mode(self) -> None:
        with self.assertRaises(BookError):
            assert_share_only({"book": {"enabled": True, "mode": "bet", "stake": False}})


if __name__ == "__main__":
    unittest.main()
