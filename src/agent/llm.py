"""
LM Studio integration for local LLM inference.
Uses OpenAI-compatible API provided by LM Studio.
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any, List, AsyncIterator
from dataclasses import dataclass
import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Response from LLM."""
    content: str
    raw_response: Dict[str, Any]
    tokens_used: int = 0
    model: str = ""
    finish_reason: str = ""


class LMStudioClient:
    """
    Client for LM Studio's OpenAI-compatible API.
    Handles chat completions for agent reasoning.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:1234/v1",
        model: str = "gemma-3-12b",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout: int = 120,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self._session

    async def close(self):
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        """
        Send a chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Override default temperature
            max_tokens: Override default max tokens
            json_mode: Request JSON output

        Returns:
            LLMResponse with generated content
        """
        session = await self._get_session()

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
        }

        # Note: json_mode removed - LM Studio doesn't support response_format
        # We'll rely on the prompt to get JSON output

        try:
            async with session.post(
                f"{self.base_url}/chat/completions",
                json=payload,
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(f"LM Studio API error: {resp.status} - {error_text}")

                data = await resp.json()

                choice = data.get("choices", [{}])[0]
                content = choice.get("message", {}).get("content", "")

                return LLMResponse(
                    content=content,
                    raw_response=data,
                    tokens_used=data.get("usage", {}).get("total_tokens", 0),
                    model=data.get("model", self.model),
                    finish_reason=choice.get("finish_reason", ""),
                )

        except aiohttp.ClientError as e:
            raise RuntimeError(f"Failed to connect to LM Studio: {e}")

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """
        Stream chat completion response.

        Args:
            messages: List of message dicts
            temperature: Override default temperature
            max_tokens: Override default max tokens

        Yields:
            Content chunks as they arrive
        """
        session = await self._get_session()

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "stream": True,
        }

        try:
            async with session.post(
                f"{self.base_url}/chat/completions",
                json=payload,
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(f"LM Studio API error: {resp.status} - {error_text}")

                async for line in resp.content:
                    line = line.decode("utf-8").strip()

                    if not line or line == "data: [DONE]":
                        continue

                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue

        except aiohttp.ClientError as e:
            raise RuntimeError(f"Failed to connect to LM Studio: {e}")

    async def get_action(
        self,
        system_prompt: str,
        viewport_state: str,
        task: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Get the next action from the LLM.

        Args:
            system_prompt: System prompt defining agent behavior
            viewport_state: Current viewport state as text
            task: User's task description
            history: Optional conversation history

        Returns:
            Parsed action dict
        """
        messages = [{"role": "system", "content": system_prompt}]

        # Add history if provided
        if history:
            messages.extend(history)

        # Build user message with current state
        user_message = f"""TASK: {task}

CURRENT VIEWPORT STATE:
{viewport_state}

Based on the current state, determine the next action to take.
Output ONLY a JSON object with your reasoning and action."""

        messages.append({"role": "user", "content": user_message})

        # Get response
        response = await self.chat(messages, json_mode=True)

        # Parse JSON response
        try:
            # Try to extract JSON from response
            content = response.content.strip()

            # Handle markdown code blocks
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1])

            action = json.loads(content)
            return action

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Response was: {response.content}")

            # Return a fallback action
            return {
                "thought": "Failed to parse response, waiting for next state",
                "action": "wait",
                "target": "",
                "value": "",
                "scroll_amount": 0,
                "mouse_path": [],
                "error": str(e),
            }

    async def check_health(self) -> bool:
        """Check if LM Studio is available."""
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/models") as resp:
                return resp.status == 200
        except Exception:
            return False

    async def list_models(self) -> List[str]:
        """List available models in LM Studio."""
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/models") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return [m.get("id", "") for m in data.get("data", [])]
        except Exception as e:
            logger.warning(f"Failed to list models: {e}")
        return []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# System prompts for different agent modes

BROWSER_AGENT_PROMPT = """You are an autonomous web-browsing agent designed to behave exactly like a human user.
Your goal is to complete tasks on a webpage using natural, human-like behavior.

BEHAVIOR RULES:
1. Scroll gradually, 200-400px at a time
2. Pause briefly after each scroll to "read" content
3. Never jump instantly to the bottom of the page
4. Move the mouse in curved, organic paths
5. Hover over elements briefly before clicking
6. Type with natural delays
7. Only interact with elements that are visible in the viewport

OUTPUT FORMAT:
You MUST output ONLY a JSON object in this exact structure:

{
  "thought": "Explain your reasoning and what you intend to do next.",
  "action": "scroll | click | type | move_mouse | wait | done",
  "target": "CSS selector or element ID if applicable",
  "value": "Text to type, if typing",
  "scroll_amount": 0,
  "mouse_path": []
}

ACTION TYPES:
- scroll: Scroll the page. Use scroll_amount (positive=down, negative=up)
- click: Click on an element. Specify target selector
- type: Type text. Specify target selector and value
- move_mouse: Move mouse to position. Use mouse_path
- wait: Wait/pause. No parameters needed
- done: Task completed

When the task is fully completed, use action "done".

CRITICAL RULES:
- NEVER output text outside the JSON
- NEVER ask questions
- NEVER say you cannot proceed
- ALWAYS decide the next action based on the viewport state
- Behave like a real human user"""


FORM_FILLER_PROMPT = """You are a specialized form-filling agent.
Your goal is to fill out web forms accurately and naturally.

You will receive:
1. The form fields visible on the page
2. Data to fill in the form
3. Current state of the form

OUTPUT FORMAT:
{
  "thought": "What field I'm filling and why",
  "action": "click | type | select | done",
  "target": "CSS selector of the field",
  "value": "Value to enter",
  "scroll_amount": 0,
  "mouse_path": []
}

Fill forms field by field, top to bottom.
Click on each field before typing.
After filling all required fields, submit the form.
Use action "done" when complete."""


NAVIGATOR_PROMPT = """You are a web navigation agent.
Your goal is to navigate to specific pages or content on websites.

You understand:
- Website structure and navigation patterns
- How to find and click links
- How to use search functionality
- When to scroll to find content

OUTPUT FORMAT:
{
  "thought": "Reasoning about navigation",
  "action": "scroll | click | type | done",
  "target": "CSS selector",
  "value": "Search text if applicable",
  "scroll_amount": 0,
  "mouse_path": []
}

Navigate step by step until you reach the target.
Use action "done" when you've reached the destination."""
