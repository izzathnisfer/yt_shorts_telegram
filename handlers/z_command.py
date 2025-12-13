"""
Num command handler - Sum of squares of digits.
"""

from telegram import Update
from telegram.ext import ContextTypes


async def num_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /num command - calculate sum of squares of digits in message."""
    if not context.args:
        await update.message.reply_text(
            "🔢 **Num Command**\n\n"
            "Calculates the sum of squares of all digits in your message.\n\n"
            "Usage: `/num <message>`\n"
            "Example: `/num hello123` → `1² + 2² + 3² = 14`",
            parse_mode='Markdown'
        )
        return
    
    text = " ".join(context.args)
    total = 0
    
    for char in text:
        if char.isdigit():
            total += int(char) ** 2
    
    await update.message.reply_text(f"`{total}`", parse_mode='Markdown')
