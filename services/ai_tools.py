"""
AI Tools for Groq LLM Integration.
Phase 1: 10-12 core tools for native Groq tool calling.
"""

from typing import List, Dict, Optional

# ============ Core Tools for Phase 1 ============
# These are passed to Groq's native tools parameter

AI_TOOLS = [
    # ============ YouTube Tools ============
    {
        "type": "function",
        "function": {
            "name": "search_youtube",
            "description": "Search for YouTube videos. Use when user wants to find videos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (e.g., 'MKBHD latest', 'funny videos')"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "download_video",
            "description": "Download a YouTube video and send to user. Use when user wants to download or get a video.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "YouTube video URL"
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "download_audio",
            "description": "Extract and download audio from YouTube video as MP3.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "YouTube video URL"
                    }
                },
                "required": ["url"]
            }
        }
    },
    
    # ============ Subscription Tools ============
    {
        "type": "function",
        "function": {
            "name": "list_subscriptions",
            "description": "Show all channels the user is subscribed to.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "subscribe_channel",
            "description": "Subscribe to a YouTube channel for notifications.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "description": "Channel name or URL to subscribe to"
                    }
                },
                "required": ["channel"]
            }
        }
    },
    
    # ============ Productivity Tools ============
    {
        "type": "function",
        "function": {
            "name": "enable_focus",
            "description": "Enable focus mode to pause all notifications. Good for studying or working.",
            "parameters": {
                "type": "object",
                "properties": {
                    "duration": {
                        "type": "string",
                        "description": "Duration like '30m', '1h', '2h'"
                    }
                },
                "required": ["duration"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "disable_focus",
            "description": "Disable focus mode and resume notifications.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_lofi_music",
            "description": "Get relaxing lofi music for studying or focus sessions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Duration in minutes (default: 30)"
                    }
                },
                "required": []
            }
        }
    },
    
    # ============ Info Tools ============
    {
        "type": "function",
        "function": {
            "name": "get_stats",
            "description": "Show user's watching statistics - videos watched, time spent, etc.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_settings",
            "description": "Show current user settings (quality, limits, quiet hours).",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_queue",
            "description": "Show the user's watch-later queue.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]


def get_tool_names() -> List[str]:
    """Get list of all available tool names."""
    return [tool["function"]["name"] for tool in AI_TOOLS]


def get_tool_by_name(name: str) -> Optional[Dict]:
    """Get a specific tool definition by name."""
    for tool in AI_TOOLS:
        if tool["function"]["name"] == name:
            return tool
    return None
