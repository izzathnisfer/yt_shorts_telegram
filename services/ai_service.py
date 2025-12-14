"""
AI Service for Groq LLM Integration.
Uses native Groq tool calling API.
"""

import json
import time
import logging
from typing import Dict, Optional, List, Any
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
    messages: List[Dict] = field(default_factory=list)
    last_activity: float = field(default_factory=time.time)
    request_count: int = 0
    request_window_start: float = field(default_factory=time.time)
    
    def add_message(self, message: Dict):
        """Add a message to the conversation."""
        self.messages.append(message)
        self.last_activity = time.time()
        # Keep only last 10 messages
        if len(self.messages) > 10:
            self.messages = self.messages[-10:]
    
    def is_expired(self) -> bool:
        return time.time() - self.last_activity > AI_CONVERSATION_TIMEOUT
    
    def is_rate_limited(self) -> bool:
        now = time.time()
        if now - self.request_window_start > 60:
            self.request_count = 0
            self.request_window_start = now
            return False
        return self.request_count >= AI_MAX_REQUESTS_PER_MINUTE
    
    def record_request(self):
        now = time.time()
        if now - self.request_window_start > 60:
            self.request_count = 1
            self.request_window_start = now
        else:
            self.request_count += 1


class AIService:
    """Main AI service using native Groq tool calling."""
    
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
        return self._client is not None and AI_ENABLED
    
    def get_conversation(self, user_id: int) -> ConversationContext:
        if user_id not in self._conversations or self._conversations[user_id].is_expired():
            self._conversations[user_id] = ConversationContext(user_id=user_id)
        return self._conversations[user_id]
    
    def clear_conversation(self, user_id: int):
        if user_id in self._conversations:
            del self._conversations[user_id]
    
    def _get_system_prompt(self, user_context: Dict[str, Any]) -> str:
        return f"""You are a friendly YouTube assistant bot. Help users find and download videos, manage subscriptions, and stay focused.

User: {user_context.get('first_name', 'Friend')}
Subscriptions: {user_context.get('subscription_count', 0)} channels
Today's videos: {user_context.get('today_count', 0)}/{user_context.get('daily_limit', 20)}

Guidelines:
- Be friendly and use emojis 🎬
- Use tools when user wants to take action
- For casual chat, just respond naturally
- Keep responses concise"""

    async def process_message(
        self,
        user_id: int,
        message: str,
        user_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process user message with native Groq tool calling."""
        if not self.is_available:
            return {"error": "AI service not available"}
        
        conversation = self.get_conversation(user_id)
        
        if conversation.is_rate_limited():
            return {
                "response": "⏳ Too many requests. Please wait a moment.",
                "error": "rate_limited"
            }
        
        conversation.record_request()
        conversation.add_message({"role": "user", "content": message})
        
        try:
            # Build messages with system prompt
            messages = [
                {"role": "system", "content": self._get_system_prompt(user_context)}
            ] + conversation.messages
            
            # Call Groq with native tools
            response = self._client.chat.completions.create(
                model=AI_MODEL_FAST,
                messages=messages,
                tools=AI_TOOLS,
                tool_choice="auto",
                temperature=AI_TEMPERATURE,
                max_tokens=AI_MAX_TOKENS_FAST,
            )
            
            assistant_message = response.choices[0].message
            
            # Check for tool calls
            if assistant_message.tool_calls:
                tool_calls = []
                for tc in assistant_message.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    
                    tool_calls.append({
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": args
                    })
                
                # Store assistant message for context
                conversation.add_message({
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in assistant_message.tool_calls
                    ]
                })
                
                return {
                    "tool_calls": tool_calls,
                    "response": None,
                    "error": None
                }
            
            # Regular text response
            text = assistant_message.content or ""
            conversation.add_message({"role": "assistant", "content": text})
            
            return {
                "response": text,
                "tool_calls": None,
                "error": None
            }
        
        except Exception as e:
            logger.error(f"AI processing error: {e}")
            return {"error": str(e)}
    
    async def send_tool_result(
        self,
        user_id: int,
        tool_call_id: str,
        tool_name: str,
        result: str,
        user_context: Dict[str, Any]
    ) -> str:
        """Send tool result back to model for final response."""
        conversation = self.get_conversation(user_id)
        
        # Add tool result to conversation
        conversation.add_message({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result
        })
        
        try:
            messages = [
                {"role": "system", "content": self._get_system_prompt(user_context)}
            ] + conversation.messages
            
            # Get final response
            response = self._client.chat.completions.create(
                model=AI_MODEL_FAST,
                messages=messages,
                temperature=AI_TEMPERATURE,
                max_tokens=AI_MAX_TOKENS_FAST,
            )
            
            text = response.choices[0].message.content or ""
            conversation.add_message({"role": "assistant", "content": text})
            
            return text
        
        except Exception as e:
            logger.error(f"Tool result processing error: {e}")
            return None


# Singleton
_ai_service: Optional[AIService] = None


def get_ai_service() -> AIService:
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService()
    return _ai_service
