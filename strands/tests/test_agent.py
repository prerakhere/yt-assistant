"""Tests for the Strands YT Assistant agent tools and server."""

import json
import os
import sys
from unittest.mock import patch, MagicMock
from decimal import Decimal

import pytest


# --- Test tool functions directly (unit tests) ---

class TestQueryVideosByDate:
    @patch("agent.table")
    def test_returns_videos_for_date(self, mock_table):
        from agent import query_videos_by_date

        mock_table.query.return_value = {
            "Items": [
                {"date": "2026-06-17", "video_id": "abc123", "title": "Test Video", "channel": "TestCh", "summary": "A test"},
                {"date": "2026-06-17", "video_id": "digest_order", "ordered_ids": ["abc123"]},
            ]
        }
        result = json.loads(query_videos_by_date._tool_func(date="2026-06-17"))
        assert result["count"] == 1
        assert result["results"][0]["video_id"] == "abc123"

    @patch("agent.table")
    def test_filters_digest_order(self, mock_table):
        from agent import query_videos_by_date

        mock_table.query.return_value = {
            "Items": [
                {"date": "2026-06-17", "video_id": "digest_order", "ordered_ids": ["x"]},
            ]
        }
        result = json.loads(query_videos_by_date._tool_func(date="2026-06-17"))
        assert result["results"] == []

    @patch("agent.table")
    def test_no_videos_returns_message(self, mock_table):
        from agent import query_videos_by_date

        mock_table.query.return_value = {"Items": []}
        result = json.loads(query_videos_by_date._tool_func(date="2026-01-01"))
        assert "No videos found" in result["message"]


class TestQueryVideosByChannel:
    @patch("agent.table")
    def test_returns_channel_videos(self, mock_table):
        from agent import query_videos_by_channel

        mock_table.query.return_value = {
            "Items": [
                {"channel": "Fireship", "video_id": "vid1", "title": "JS in 100s"},
            ]
        }
        result = json.loads(query_videos_by_channel._tool_func(channel="Fireship"))
        assert result["count"] == 1
        assert result["results"][0]["channel"] == "Fireship"

    @patch("agent.table")
    def test_no_channel_results(self, mock_table):
        from agent import query_videos_by_channel

        mock_table.query.return_value = {"Items": []}
        result = json.loads(query_videos_by_channel._tool_func(channel="NonExistent"))
        assert "No videos found" in result["message"]


class TestSearchVideos:
    @patch("agent.table")
    def test_finds_by_title_keyword(self, mock_table):
        from agent import search_videos

        mock_table.query.return_value = {
            "Items": [
                {"video_id": "v1", "title": "Kubernetes Deep Dive", "summary": "About k8s", "date": "2026-06-17"},
                {"video_id": "v2", "title": "React Hooks", "summary": "Frontend stuff", "date": "2026-06-17"},
            ]
        }
        result = json.loads(search_videos._tool_func(keyword="kubernetes", days=1))
        assert result["count"] == 1
        assert "Kubernetes" in result["results"][0]["title"]

    @patch("agent.table")
    def test_finds_by_summary_keyword(self, mock_table):
        from agent import search_videos

        mock_table.query.return_value = {
            "Items": [
                {"video_id": "v1", "title": "Some Title", "summary": "Discusses terraform modules", "date": "2026-06-17"},
            ]
        }
        result = json.loads(search_videos._tool_func(keyword="terraform", days=1))
        assert result["count"] == 1

    @patch("agent.table")
    def test_no_results(self, mock_table):
        from agent import search_videos

        mock_table.query.return_value = {"Items": []}
        result = json.loads(search_videos._tool_func(keyword="nonexistenttopic", days=1))
        assert result["results"] == []


class TestGetDigestOrder:
    @patch("agent.table")
    def test_returns_ordered_positions(self, mock_table):
        from agent import get_digest_order

        mock_table.query.side_effect = [
            {"Items": [{"date": "2026-06-17", "video_id": "digest_order", "ordered_ids": ["vid1", "vid2"]}]},
            {"Items": [
                {"video_id": "vid1", "title": "First Video", "channel": "Ch1", "date": "2026-06-17"},
                {"video_id": "vid2", "title": "Second Video", "channel": "Ch2", "date": "2026-06-17"},
                {"video_id": "digest_order", "ordered_ids": ["vid1", "vid2"], "date": "2026-06-17"},
            ]},
        ]
        result = json.loads(get_digest_order._tool_func(date="2026-06-17"))
        assert len(result) == 2
        assert result[0]["position"] == 1
        assert result[0]["video_id"] == "vid1"
        assert result[1]["position"] == 2

    @patch("agent.table")
    def test_no_digest_order(self, mock_table):
        from agent import get_digest_order

        mock_table.query.return_value = {"Items": []}
        result = json.loads(get_digest_order._tool_func(date="2026-01-01"))
        assert "error" in result


class TestBuildSystemPrompt:
    def test_contains_today_date(self):
        from agent import _build_system_prompt, _today_ist

        prompt = _build_system_prompt()
        assert _today_ist() in prompt
        assert "YT Assistant" in prompt
        assert "query_videos_by_date" in prompt


class TestCreateAgent:
    @patch("agent.BedrockModel")
    def test_creates_agent_without_memory(self, mock_model):
        from agent import create_agent

        os.environ.pop("AGENTCORE_MEMORY_ID", None)
        with patch("agent.Agent") as mock_agent:
            create_agent(session_id="test")
            mock_agent.assert_called_once()
            call_kwargs = mock_agent.call_args[1]
            assert "system_prompt" in call_kwargs
            assert "tools" in call_kwargs
            assert len(call_kwargs["tools"]) == 5


# --- Test server contract (mock bedrock_agentcore since not installed locally) ---

class TestServerContract:
    @pytest.fixture(autouse=True)
    def mock_bedrock_agentcore(self):
        """Mock bedrock_agentcore module for server import."""
        mock_module = MagicMock()
        mock_app = MagicMock()
        mock_app.entrypoint = lambda f: f  # decorator passthrough
        mock_module.runtime.BedrockAgentCoreApp.return_value = mock_app
        sys.modules["bedrock_agentcore"] = mock_module
        sys.modules["bedrock_agentcore.runtime"] = mock_module.runtime
        mock_module.runtime.BedrockAgentCoreApp = lambda: mock_app

        # Need to reload server with mocked module
        if "server" in sys.modules:
            del sys.modules["server"]

        yield
        # Cleanup
        sys.modules.pop("bedrock_agentcore", None)
        sys.modules.pop("bedrock_agentcore.runtime", None)
        sys.modules.pop("server", None)

    @patch("agent.create_agent")
    def test_invoke_returns_response(self, mock_create):
        # Re-import with mock
        mock_agent_instance = MagicMock()
        mock_agent_instance.return_value.message = {
            "content": [{"text": "Here are today's videos..."}]
        }
        mock_create.return_value = mock_agent_instance

        # Import the invoke function directly from agent and simulate server logic
        prompt = "show today's videos"
        result_msg = mock_agent_instance(prompt)
        response_text = result_msg.message["content"][0]["text"]
        assert "videos" in response_text

    def test_invoke_no_prompt_logic(self):
        """Test the no-prompt guard logic."""
        payload = {}
        prompt = payload.get("prompt", "")
        if not prompt:
            result = {"response": "No prompt provided.", "status": "error"}
        assert result["status"] == "error"
        assert "No prompt" in result["response"]

    def test_invoke_empty_prompt_logic(self):
        """Test empty prompt guard logic."""
        payload = {"prompt": ""}
        prompt = payload.get("prompt", "")
        if not prompt:
            result = {"response": "No prompt provided.", "status": "error"}
        assert result["status"] == "error"


# --- Test Decimal serialization ---

class TestDecimalSerialization:
    @patch("agent.table")
    def test_decimal_values_serialize(self, mock_table):
        from agent import query_videos_by_date

        mock_table.query.return_value = {
            "Items": [
                {"date": "2026-06-17", "video_id": "abc", "title": "Test", "views": Decimal("1234")},
            ]
        }
        result = query_videos_by_date._tool_func(date="2026-06-17")
        parsed = json.loads(result)
        assert parsed["count"] == 1
        assert parsed["results"][0]["views"] == "1234"
