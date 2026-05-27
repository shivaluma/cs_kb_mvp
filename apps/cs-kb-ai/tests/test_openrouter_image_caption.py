from __future__ import annotations

import unittest
from unittest.mock import patch

from app import openrouter


class FakeResponse:
    def __init__(self, body: dict) -> None:
        self.body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.body


class FakeClient:
    def __init__(self, body: dict) -> None:
        self.body = body
        self.payloads: list[dict] = []

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def post(self, url: str, headers: dict, json: dict) -> FakeResponse:
        self.payloads.append(json)
        return FakeResponse(self.body)


class OpenRouterImageCaptionTest(unittest.TestCase):
    def test_describe_image_asset_sends_image_url_and_parses_caption(self) -> None:
        client = FakeClient(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"caption":"Refund workflow screenshot with approval steps.","confidence":0.82,"warnings":["needs_review"]}'
                        }
                    }
                ]
            }
        )

        with patch.object(openrouter.settings, "openrouter_api_key", "key"), \
            patch.object(openrouter.settings, "openrouter_base_url", "https://openrouter.ai/api/v1"), \
            patch.object(openrouter.settings, "openrouter_vision_model", "vision-model"), \
            patch("app.openrouter.httpx.Client", return_value=client):
            caption, warnings, error = openrouter.describe_image_asset(
                filename="flow.png",
                content_type="image/png",
                image_data_url="data:image/png;base64,abc",
            )

        self.assertEqual(error, "")
        self.assertEqual(caption["text"], "Refund workflow screenshot with approval steps.")
        self.assertEqual(caption["confidence"], 0.82)
        self.assertEqual(caption["model"], "vision-model")
        self.assertIn("needs_review", warnings)
        user_content = client.payloads[0]["messages"][1]["content"]
        self.assertTrue(any(item.get("type") == "image_url" for item in user_content))


if __name__ == "__main__":
    unittest.main()
