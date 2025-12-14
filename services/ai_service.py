"""
AI Service for Groq LLM Integration.
Handles LLM calls, tool execution, and conversation management.
"""

import json
import time
import logging
from typing import Dict, Optional, List, Any, Callable
from dataclasses import dataclass, field

from groq import Groq

from config import (
    GROQ_API_KEY, AI_ENABLED,
    AI_MODEL_FAST, AI_MODEL_SMART,
    AI_MAX_TOKENS_FAST, AI_MAX_TOKENS_SMART,
    AI_TEMPERATURE, AI_MAX_REQUESTS_PER_MINUTE,
    AI_CONVERSATION_TIMEOUT
)
from .ai_tools import AI_TOOLS

logger = logging.getLogger(__name__)


@dataclass
class ConversationContext:
    """Stores conversation history for a user."""
    user_id: int
    messages: List[Dict[str, str]] = field(default_factory=list)
    last_activity: float = field(default_factory=time.time)
    request_count: int = 0
    request_window_start: float = field(default_factory=time.time)
    
    def add_message(self, role: str, content: str):
        """Add a message to the conversation."""
        self.messages.append({"role": role, "content": content})
        self.last_activity = time.time()
        # Keep only last 10 messages for context
        if len(self.messages) > 10:
            self.messages = self.messages[-10:]
    
    def is_expired(self) -> bool:
        """Check if conversation has timed out."""
        return time.time() - self.last_activity > AI_CONVERSATION_TIMEOUT
    
    def is_rate_limited(self) -> bool:
        """Check if user has exceeded rate limit."""
        now = time.time()
        if now - self.request_window_start > 60:
            self.request_count = 0
            self.request_window_start = now
            return False
        return self.request_count >= AI_MAX_REQUESTS_PER_MINUTE
    
    def record_request(self):
        """Record a new request for rate limiting."""
        now = time.time()
        if now - self.request_window_start > 60:
            self.request_count = 1
            self.request_window_start = now
        else:
            self.request_count += 1


class AIService:
    """Main AI service for handling LLM interactions."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._client: Optional[Groq] = None
        self._conversations: Dict[int, ConversationContext] = {}
        
        if GROQ_API_KEY and AI_ENABLED:
            try:
                self._client = Groq(api_key=GROQ_API_KEY)
                logger.info("Groq AI client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Groq client: {e}")
    
    @property
    def is_available(self) -> bool:
        """Check if AI service is available."""
        return self._client is not None and AI_ENABLED
    
    def get_conversation(self, user_id: int) -> ConversationContext:
        """Get or create conversation context for a user."""
        if user_id not in self._conversations or self._conversations[user_id].is_expired():
            self._conversations[user_id] = ConversationContext(user_id=user_id)
        return self._conversations[user_id]
    
    def clear_conversation(self, user_id: int):
        """Clear conversation history for a user."""
        if user_id in self._conversations:
            del self._conversations[user_id]
    
    def _get_system_prompt(self, user_context: Dict[str, Any]) -> str:
        """Generate system prompt with user context."""
        return f"""You are the YouTube Shorts Bot AI assistant. Help users manage their YouTube experience.

## User: {user_context.get('first_name', 'User')}
- Subscriptions: {user_context.get('subscription_count', 0)} channels
- Today's videos: {user_context.get('today_count', 0)}/{user_context.get('daily_limit', 20)}
- Focus mode: {'Active' if user_context.get('is_focus') else 'Inactive'}

## CRITICAL RULES:
1. For actions, respond with ONLY the JSON object, nothing else: {{"tool": "name", "args": {{}}}}
2. For normal chat, respond with just text, no JSON.
3. NEVER mix text and JSON in the same response.

## Available tools:
- search_youtube: {{"tool": "search_youtube", "args": {{"query": "search term"}}}}
- download_video: {{"tool": "download_video", "args": {{"url": "youtube.com/..."}}}}
- download_audio: {{"tool": "download_audio", "args": {{"url": "youtube.com/..."}}}}
- list_subscriptions: {{"tool": "list_subscriptions", "args": {{}}}}
- get_stats: {{"tool": "get_stats", "args": {{}}}}
- enable_focus: {{"tool": "enable_focus", "args": {{"duration": "30m"}}}}
- disable_focus: {{"tool": "disable_focus", "args": {{}}}}
- get_lofi_music: {{"tool": "get_lofi_music", "args": {{"duration_minutes": 30}}}}

## Examples:
User: "Hi!" → You: "Hello! 👋 How can I help you today?"
User: "Search MKBHD" → You: {{"tool": "search_youtube", "args": {{"query": "MKBHD"}}}}
User: "Show stats" → You: {{"tool": "get_stats", "args": {{}}}}
User: "I'm bored" → You: "What kind of content interests you? Music, tutorials, gaming?"
User: "yes music" → You: {{"tool": "search_youtube", "args": {{"query": "music videos"}}}}
"""

    async def process_message(
        self,
        user_id: int,
        message: str,
        user_context: Dict[str, Any],
        use_smart_model: bool = False
    ) -> Dict[str, Any]:
        """
        Process a user message and return AI response.
        Uses simple JSON response format instead of native tool calling for compatibility.
        """
        if not self.is_available:
            return {
                "response": None,
                "tool_call": None,
                "error": "AI service is not available"
            }
        
        conversation = self.get_conversation(user_id)
        
        # Check rate limiting
        if conversation.is_rate_limited():
            return {
                "response": "⏳ You're sending too many requests. Please wait a moment.",
                "tool_call": None,
                "error": "rate_limited"
            }
        
        conversation.record_request()
        conversation.add_message("user", message)
        
        # Use the fast model by default - better for simple conversations
        model = AI_MODEL_SMART if use_smart_model else AI_MODEL_FAST
        max_tokens = AI_MAX_TOKENS_SMART if use_smart_model else AI_MAX_TOKENS_FAST
        
        try:
            # Build messages list with system prompt
            messages = [
                {"role": "system", "content": self._get_system_prompt(user_context)}
            ] + conversation.messages
            
            # Simple chat completion without tool calling
            response = self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=AI_TEMPERATURE,
                max_tokens=max_tokens,
            )
            
            content = response.choices[0].message.content
            
            if not content:
                return {
                    "response": None,
                    "tool_call": None,
                    "error": "Empty response from AI"
                }
            
            conversation.add_message("assistant", content)
            
            # Check if response contains a tool call (JSON format)
            tool_call = self._parse_tool_call(content)
            
            if tool_call:
                return {
                    "response": None,
                    "tool_call": tool_call,
                    "error": None,
                    "model_used": model
                }
            else:
                # It's a regular text response
                return {
                    "response": content,
                    "tool_call": None,
                    "error": None,
                    "model_used": model
                }
        
        except Exception as e:
            logger.error(f"AI processing error: {e}")
            return {
                "response": None,
                "tool_call": None,
                "error": str(e)
            }
    
    def _parse_tool_call(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse tool call from AI response if present."""
        import re
        
        content = content.strip()
        
        # Try 1: Check if entire response is JSON
        if content.startswith('{') and content.endswith('}'):
            try:
                data = json.loads(content)
                if "tool" in data:
                    return {
                        "name": data.get("tool"),
                        "arguments": data.get("args", {})
                    }
            except json.JSONDecodeError:
                pass
        
        # Try 2: Extract JSON object from within text
        # Look for {"tool": ...} pattern anywhere in the text
        json_pattern = r'\{[^{}]*"tool"[^{}]*\}'
        matches = re.findall(json_pattern, content)
        
        for match in matches:
            try:
                data = json.loads(match)
                if "tool" in data:
                    return {
                        "name": data.get("tool"),
                        "arguments": data.get("args", {})
                    }
            except json.JSONDecodeError:
                continue
        
        # Try 3: Find JSON with nested braces (for args with values)
        # Match from {"tool" to the matching closing brace
        start_idx = content.find('{"tool"')
        if start_idx == -1:
            start_idx = content.find("{'tool'")
        
        if start_idx != -1:
            brace_count = 0
            end_idx = start_idx
            for i, char in enumerate(content[start_idx:], start_idx):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break
            
            if end_idx > start_idx:
                try:
                    json_str = content[start_idx:end_idx]
                    data = json.loads(json_str)
                    if "tool" in data:
                        return {
                            "name": data.get("tool"),
                            "arguments": data.get("args", {})
                        }
                except json.JSONDecodeError:
                    pass
        
        return None


# Singleton instance
_ai_service: Optional[AIService] = None


def get_ai_service() -> AIService:
    """Get the singleton AI service instance."""
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService()
    return _ai_service
