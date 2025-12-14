"""
AI Service for Groq LLM Integration.
Handles LLM calls, tool execution, and conversation management.
"""

import json
import time
import logging
from typing import Dict, Optional, List, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from groq import Groq, AsyncGroq

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
        # Reset window if more than a minute has passed
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
        self._tool_handlers: Dict[str, Callable] = {}
        
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
    
    def register_tool_handler(self, name: str, handler: Callable):
        """Register a handler function for a tool."""
        self._tool_handlers[name] = handler
        logger.debug(f"Registered tool handler: {name}")
    
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
- Manage channel subscriptions (subscribe, unsubscribe, set priority/nickname)
- Manage watch queue and favorites
- Configure user settings (quality, limits, quiet hours)
- Enable focus mode for distraction-free work
- Provide watching statistics and insights
- Download files from URLs (leech feature)

## User Context:
- Name: {user_context.get('first_name', 'User')}
- Subscriptions: {user_context.get('subscription_count', 0)} channels
- Today's videos: {user_context.get('today_count', 0)}/{user_context.get('daily_limit', 20)}
- Focus mode: {'Active' if user_context.get('is_focus') else 'Inactive'}

## Guidelines:
1. Be friendly and use emojis appropriately 🎬
2. Always confirm before destructive actions (unsubscribe, clear queue)
3. Suggest focus mode when user seems overwhelmed
4. Recommend lofi music for study/work sessions
5. Keep responses concise for mobile reading
6. If user wants to download a video, search first if no URL provided
7. Format lists and stats nicely with emojis

## Important:
- Use tool calls to execute actions, don't just describe them
- For simple greetings/questions, use send_message tool
- If user's request is unclear, ask for clarification
"""

    async def process_message(
        self,
        user_id: int,
        message: str,
        user_context: Dict[str, Any],
        use_smart_model: bool = False
    ) -> Dict[str, Any]:
        """
        Process a user message and return AI response with tool calls.
        
        Returns:
            Dict with 'response' (text), 'tool_calls' (list), and 'error' (if any)
        """
        if not self.is_available:
            return {
                "response": None,
                "tool_calls": [],
                "error": "AI service is not available"
            }
        
        conversation = self.get_conversation(user_id)
        
        # Check rate limiting
        if conversation.is_rate_limited():
            return {
                "response": "⏳ You're sending too many requests. Please wait a moment.",
                "tool_calls": [],
                "error": "rate_limited"
            }
        
        conversation.record_request()
        conversation.add_message("user", message)
        
        # Choose model based on complexity
        model = AI_MODEL_SMART if use_smart_model else AI_MODEL_FAST
        max_tokens = AI_MAX_TOKENS_SMART if use_smart_model else AI_MAX_TOKENS_FAST
        
        try:
            # Build messages list with system prompt
            messages = [
                {"role": "system", "content": self._get_system_prompt(user_context)}
            ] + conversation.messages
            
            # Call Groq API
            response = self._client.chat.completions.create(
                model=model,
                messages=messages,
                tools=AI_TOOLS,
                tool_choice="auto",
                temperature=AI_TEMPERATURE,
                max_tokens=max_tokens,
            )
            
            assistant_message = response.choices[0].message
            tool_calls = []
            text_response = None
            
            # Handle tool calls
            if assistant_message.tool_calls:
                for tool_call in assistant_message.tool_calls:
                    tool_name = tool_call.function.name
                    try:
                        tool_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        tool_args = {}
                    
                    tool_calls.append({
                        "id": tool_call.id,
                        "name": tool_name,
                        "arguments": tool_args
                    })
                    
                    logger.info(f"AI tool call: {tool_name}({tool_args})")
            
            # Get text content if any
            if assistant_message.content:
                text_response = assistant_message.content
                conversation.add_message("assistant", text_response)
            
            return {
                "response": text_response,
                "tool_calls": tool_calls,
                "error": None,
                "model_used": model
            }
        
        except Exception as e:
            logger.error(f"AI processing error: {e}")
            return {
                "response": None,
                "tool_calls": [],
                "error": str(e)
            }
    
    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        user_id: int,
        context: Any = None
    ) -> Dict[str, Any]:
        """
        Execute a tool and return the result.
        
        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments
            user_id: User ID for context
            context: Telegram context object
            
        Returns:
            Dict with 'success', 'result', and 'error'
        """
        if tool_name not in self._tool_handlers:
            return {
                "success": False,
                "result": None,
                "error": f"Unknown tool: {tool_name}"
            }
        
        try:
            handler = self._tool_handlers[tool_name]
            result = await handler(user_id=user_id, context=context, **arguments)
            
            return {
                "success": True,
                "result": result,
                "error": None
            }
        except Exception as e:
            logger.error(f"Tool execution error ({tool_name}): {e}")
            return {
                "success": False,
                "result": None,
                "error": str(e)
            }
    
    async def get_follow_up_response(
        self,
        user_id: int,
        tool_results: List[Dict[str, Any]],
        user_context: Dict[str, Any]
    ) -> str:
        """
        Get AI response after tool execution to format results nicely.
        """
        if not self.is_available or not tool_results:
            return None
        
        conversation = self.get_conversation(user_id)
        
        # Add tool results to conversation
        results_summary = "\n".join([
            f"Tool: {r.get('name')}\nResult: {json.dumps(r.get('result', {}), indent=2)}"
            for r in tool_results
        ])
        
        conversation.add_message(
            "user", 
            f"[System: Tool execution completed]\n{results_summary}\n\nPlease summarize the results nicely for the user."
        )
        
        try:
            messages = [
                {"role": "system", "content": self._get_system_prompt(user_context)}
            ] + conversation.messages
            
            response = self._client.chat.completions.create(
                model=AI_MODEL_FAST,
                messages=messages,
                temperature=AI_TEMPERATURE,
                max_tokens=AI_MAX_TOKENS_FAST,
            )
            
            result = response.choices[0].message.content
            if result:
                conversation.add_message("assistant", result)
            return result
        
        except Exception as e:
            logger.error(f"Follow-up response error: {e}")
            return None


# Singleton instance
_ai_service: Optional[AIService] = None


def get_ai_service() -> AIService:
    """Get the singleton AI service instance."""
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService()
    return _ai_service
