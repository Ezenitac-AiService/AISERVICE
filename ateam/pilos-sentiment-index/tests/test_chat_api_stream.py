import json
import unittest

from pilos.web.app import app


class ChatApiStreamTest(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_json_mode_returns_200_json(self):
        response = self.client.post(
            "/api/chat",
            json={
                "block_key": "service_overview",
                "session_id": "test-session",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "application/json")
        body = response.get_json()
        self.assertEqual(body["status"], "ready")
        self.assertEqual(body["route"], "service_knowledge")
        self.assertIn("PILOS", body["answer"])

    def test_sse_streaming_mode_returns_event_stream(self):
        response = self.client.post(
            "/api/chat",
            json={
                "block_key": "service_overview",
                "session_id": "test-session-sse",
                "stream": True,
            },
            headers={"Accept": "text/event-stream"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.content_type)

        lines = response.get_data(as_text=True).strip().split("\n\n")
        events = []
        for line in lines:
            if line.startswith("data: "):
                data_str = line[6:]
                if data_str == "[DONE]":
                    events.append("[DONE]")
                else:
                    events.append(json.loads(data_str))

        self.assertTrue(len(events) >= 2)
        # Check token event
        token_events = [e for e in events if isinstance(e, dict) and e.get("type") == "token"]
        self.assertTrue(len(token_events) > 0)

        # Check done event
        done_events = [e for e in events if isinstance(e, dict) and e.get("type") == "done"]
        self.assertEqual(len(done_events), 1)
        self.assertEqual(done_events[0]["status"], "ready")
        self.assertEqual(done_events[0]["route"], "service_knowledge")
        self.assertTrue(len(done_events[0]["sources"]) >= 1)

        # Check [DONE] terminator
        self.assertEqual(events[-1], "[DONE]")

    def test_fixed_stock_chat_sse_stream(self):
        response = self.client.post(
            "/api/stocks/005930/chat",
            json={
                "block_key": "service_models",
                "session_id": "test-stock-sse",
                "stream": True,
            },
            headers={"Accept": "text/event-stream"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.content_type)


if __name__ == "__main__":
    unittest.main()
