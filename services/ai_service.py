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
        return f"""You are the YouTube Shorts Bot AI assistant. You help users manage their YouTube experience mindfully.

## Your Capabilities:
- Search and download YouTube videos/audio
- Manage channel subscriptions
- Manage watch queue and favorites
- Configure user settings
- Enable focus mode for distraction-free work
- Provide watching statistics

## User Context:
- Name: {user_context.get('first_name', 'User')}
- Subscriptions: {user_context.get('subscription_count', 0)} channels
- Today's videos: {user_context.get('today_count', 0)}/{user_context.get('daily_limit', 20)}
- Focus mode: {'Active' if user_context.get('is_focus') else 'Inactive'}

## Guidelines:
1. Be friendly and use emojis appropriately 🎬
2. Keep responses concise for mobile reading
3. When user wants to perform an action, respond with a JSON tool call in this format:
   {{"tool": "tool_name", "args": {{"param": "value"}}}}
4. Available tools: search_youtube, download_video, download_audio, list_subscriptions, enable_focus, disable_focus, get_stats, get_lofi_music
5. For simple greetings or questions, just respond naturally without JSON.

## Examples:
User: "Hi!"
You: "Hello! 👋 I'm your YouTube assistant. How can I help you today?"

User: "Search for MKBHD"
You: {{"tool": "search_youtube", "args": {{"query": "MKBHD"}}}}

User: "Show my stats"
You: {{"tool": "get_stats", "args": {{}}}}

User: "Enable focus for 30 minutes"  
You: {{"tool": "enable_focus", "args": {{"duration": "30m"}}}}
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
        content = content.strip()
        
        # Check if the response looks like JSON
        if not (content.startswith('{') and content.endswith('}')):
            return None
        
        try:
            data = json.loads(content)
            
            # Check if it has the expected tool call format
            if "tool" in data:
                return {
                    "name": data.get("tool"),
                    "arguments": data.get("args", {})
                }
            
            return None
        except json.JSONDecodeError:
            return None


# Singleton instance
_ai_service: Optional[AIService] = None


def get_ai_service() -> AIService:
    """Get the singleton AI service instance."""
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService()
    return _ai_service
