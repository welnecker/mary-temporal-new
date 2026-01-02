import sys
import unittest
from unittest.mock import MagicMock, patch

# Define modules that need to be mocked
MOCK_MODULES = [
    "streamlit",
    "core.service_router",
    "core.canon",
    "core.relationship_engine",
    "core.repositories",
    "core.nsfw",
    "characters.registry",
]

# Create mocks
for mod_name in MOCK_MODULES:
    sys.modules[mod_name] = MagicMock()

# Configure streamlit mock specifically
import streamlit as st
st.session_state = {}

# Mock relationship_engine configuration
from core.relationship_engine import EngineConfig
sys.modules["core.relationship_engine"].EngineConfig = MagicMock()
sys.modules["core.relationship_engine"].default_relationship_state = lambda tl: {}

# Import MaryService after mocks
from characters.mary.service import MaryService

class TestMaryService(unittest.TestCase):
    def setUp(self):
        # Reset session state
        st.session_state.clear()

        # Setup specific mocks
        self.mock_repo = sys.modules["core.repositories"]
        self.mock_repo.get_facts.return_value = {}
        self.mock_repo.get_history_docs.return_value = []
        self.mock_repo.list_memories.return_value = []

        self.mock_router = sys.modules["core.service_router"]
        # Mock chat response: returns (response_json, used_model, metadata)
        self.mock_router.route_chat_strict.return_value = (
            {"choices": [{"message": {"content": "Olá, sou Mary."}}]},
            "mock-model",
            {}
        )

        self.mock_nsfw = sys.modules["core.nsfw"]
        self.mock_nsfw.nsfw_enabled.return_value = False

    def test_mary_initialization(self):
        service = MaryService()
        self.assertEqual(service.display_name, "Mary")

    def test_mary_reply(self):
        service = MaryService()

        # Mocking facts to avoid initialization issues
        # Providing necessary keys for MaryService.reply logic
        self.mock_repo.get_facts.return_value = {
            "cena.locked": True,
            "intimacy.phase": 0
        }

        reply = service.reply(
            user="Janio",
            model="mock-model",
            prompt="Oi Mary",
            timeline="cumplice",
            nsfw=False
        )

        self.assertEqual(reply, "Olá, sou Mary.")
        self.mock_router.route_chat_strict.assert_called()

if __name__ == "__main__":
    unittest.main()
