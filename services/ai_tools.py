"""
AI Tools for Groq LLM Integration.
Defines all available tools (functions) that the AI can call.
"""

from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


# ============ Tool Definitions for Groq ============
# These are passed to the LLM to describe available functions

AI_TOOLS = [
    # ============ YouTube Tools ============
    {
        "type": "function",
        "function": {
            "name": "search_youtube",
            "description": "Search for YouTube videos by query. Returns a list of video results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (e.g., 'MKBHD latest', 'python tutorial')"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 5)",
                        "default": 5
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
            "description": "Download a YouTube video. Can optionally trim to specific time range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "YouTube video URL"
                    },
                    "quality": {
                        "type": "string",
                        "enum": ["360", "480", "720", "1080"],
                        "description": "Video quality (default: user's setting)",
                        "default": "720"
                    },
                    "trim_start": {
                        "type": "string",
                        "description": "Start time for trim (format: MM:SS or HH:MM:SS)"
                    },
                    "trim_end": {
                        "type": "string",
                        "description": "End time for trim (format: MM:SS or HH:MM:SS)"
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
            "description": "Download audio only from a YouTube video as MP3.",
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
            "name": "get_video_info",
            "description": "Get information about a YouTube video (title, duration, channel, etc.)",
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
            "name": "get_lofi_music",
            "description": "Get lofi study music for a specified duration. Great for focus sessions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Desired duration in minutes (15, 30, 45, 60, etc.)",
                        "default": 30
                    }
                },
                "required": []
            }
        }
    },
    
    # ============ Subscription Tools ============
    {
        "type": "function",
        "function": {
            "name": "subscribe_channel",
            "description": "Subscribe to a YouTube channel to get notifications for new videos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "description": "Channel name or YouTube channel URL"
                    }
                },
                "required": ["channel"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "unsubscribe_channel",
            "description": "Unsubscribe from a YouTube channel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel_name": {
                        "type": "string",
                        "description": "Name of the channel to unsubscribe from"
                    }
                },
                "required": ["channel_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_subscriptions",
            "description": "Get list of all subscribed channels.",
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
            "name": "set_channel_priority",
            "description": "Set a channel as priority (will notify even during quiet hours).",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel_name": {
                        "type": "string",
                        "description": "Name of the channel"
                    },
                    "is_priority": {
                        "type": "boolean",
                        "description": "True to set as priority, False to remove priority"
                    }
                },
                "required": ["channel_name", "is_priority"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_channel_nickname",
            "description": "Set a custom nickname for a channel (for easier reference).",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel_name": {
                        "type": "string",
                        "description": "Current name of the channel"
                    },
                    "nickname": {
                        "type": "string",
                        "description": "Custom nickname to set (or empty to remove)"
                    }
                },
                "required": ["channel_name", "nickname"]
            }
        }
    },
    
    # ============ Queue & Favorites Tools ============
    {
        "type": "function",
        "function": {
            "name": "add_to_queue",
            "description": "Add a video to the watch later queue.",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_url": {
                        "type": "string",
                        "description": "YouTube video URL to add to queue"
                    }
                },
                "required": ["video_url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_queue",
            "description": "Get the current watch later queue.",
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
            "name": "clear_queue",
            "description": "Clear all videos from the watch queue. Destructive action - confirm first!",
            "parameters": {
                "type": "object",
                "properties": {
                    "confirmed": {
                        "type": "boolean",
                        "description": "Must be true to confirm clearing"
                    }
                },
                "required": ["confirmed"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sync_queue",
            "description": "Download all videos in the queue at once (bulk download).",
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
            "name": "add_favorite",
            "description": "Add a video to favorites for easy access later.",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_url": {
                        "type": "string",
                        "description": "YouTube video URL to add to favorites"
                    }
                },
                "required": ["video_url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_favorites",
            "description": "Get list of favorite videos.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    
    # ============ Settings Tools ============
    {
        "type": "function",
        "function": {
            "name": "get_settings",
            "description": "Get current user settings (quality, limits, quiet hours, etc.)",
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
            "name": "set_quality",
            "description": "Set preferred video download quality.",
            "parameters": {
                "type": "object",
                "properties": {
                    "quality": {
                        "type": "string",
                        "enum": ["360", "480", "720", "1080"],
                        "description": "Video quality"
                    }
                },
                "required": ["quality"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_daily_limit",
            "description": "Set maximum videos per day (0 for unlimited).",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum videos per day (0 = unlimited)"
                    }
                },
                "required": ["limit"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_quiet_hours",
            "description": "Set quiet hours (no notifications during this time).",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_time": {
                        "type": "string",
                        "description": "Start time in HH:MM format (e.g., '23:00')"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End time in HH:MM format (e.g., '07:00')"
                    }
                },
                "required": ["start_time", "end_time"]
            }
        }
    },
    
    # ============ Focus & Productivity Tools ============
    {
        "type": "function",
        "function": {
            "name": "enable_focus",
            "description": "Enable focus mode to pause all notifications for a duration.",
            "parameters": {
                "type": "object",
                "properties": {
                    "duration": {
                        "type": "string",
                        "description": "Duration (e.g., '30m', '1h', '2h')"
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
            "name": "get_focus_status",
            "description": "Check if focus mode is active and remaining time.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    
    # ============ Statistics Tools ============
    {
        "type": "function",
        "function": {
            "name": "get_stats",
            "description": "Get comprehensive watching statistics (today, weekly, all-time).",
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
            "name": "get_today_stats",
            "description": "Get today's watching statistics.",
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
            "name": "get_top_channels",
            "description": "Get most watched channels by time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of top channels to return",
                        "default": 5
                    }
                },
                "required": []
            }
        }
    },
    
    # ============ Leech (URL Download) Tools ============
    {
        "type": "function",
        "function": {
            "name": "leech_to_telegram",
            "description": "Download a file from any URL and send to Telegram.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Direct URL to download"
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "leech_to_nextcloud",
            "description": "Download a file from any URL and upload to Nextcloud.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Direct URL to download"
                    }
                },
                "required": ["url"]
            }
        }
    },
    
    # ============ Utility Tools ============
    {
        "type": "function",
        "function": {
            "name": "get_help",
            "description": "Get help information about bot features and commands.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Specific topic (subscriptions, downloads, settings, etc.)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "Send a text message response to the user. Use this for conversational responses.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Message to send to the user"
                    }
                },
                "required": ["message"]
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


def format_tools_for_prompt() -> str:
    """Format tools as a readable list for the system prompt."""
    lines = ["Available tools:"]
    for tool in AI_TOOLS:
        func = tool["function"]
        name = func["name"]
        desc = func["description"]
        lines.append(f"- {name}: {desc}")
    return "\n".join(lines)
