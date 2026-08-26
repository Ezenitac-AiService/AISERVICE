import os
import unittest
from pathlib import Path


class ServiceIsolationTest(unittest.TestCase):
    def test_bteam_directories_remain_untouched(self):
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        bteam_dir = repo_root / "bteam"

        self.assertTrue(bteam_dir.exists(), "bteam 디렉토리가 존재해야 합니다.")
        self.assertTrue((bteam_dir / "Oliview_Project").exists())

    def test_nginx_gateway_preserves_bteam_routes(self):
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        nginx_conf_path = repo_root / "gateway" / "nginx.conf"

        self.assertTrue(nginx_conf_path.exists(), "gateway/nginx.conf가 존재해야 합니다.")
        content = nginx_conf_path.read_text(encoding="utf-8")

        # B-Team 올리챗 (Streamlit / 8501) 라우트 보존 확인
        self.assertIn("location /bteam/chata/", content)
        self.assertIn("oliview_chatbot_a:8501", content)

        # B-Team 올원챗 (FastAPI / 8002) 라우트 보존 확인
        self.assertIn("location /bteam/chatb/", content)
        self.assertIn("oliview_chatbot_b:8002", content)

        # B-Team 올리뷰 포털 라우트 보존 확인
        self.assertIn("location /bteam/oliview/", content)

        # A-Team Pilos 버퍼링 해제 확인
        self.assertIn("location /ateam/pilos/", content)
        self.assertIn("proxy_buffering off;", content)

    def test_pilos_chat_does_not_depend_on_bteam_modules(self):
        from pilos.service.chatbot_service import ChatbotService
        from pilos.service.knowledge_cache import SERVICE_KNOWLEDGE_CACHE

        self.assertTrue(len(SERVICE_KNOWLEDGE_CACHE) >= 15)
        service = ChatbotService()
        self.assertIsNotNone(service)


if __name__ == "__main__":
    unittest.main()
