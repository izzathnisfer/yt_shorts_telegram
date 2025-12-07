"""
Export/Import command handlers - Data portability.
"""

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters
import json
import tempfile
import os

from database import export_user_data, import_user_data
from tg_bot.keyboards import back_button


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /export command."""
    user_id = update.effective_user.id
    
    loading = await update.message.reply_text("📦 Exporting your data...")
    
    try:
        # Export data
        data = await export_user_data(user_id)
        
        # Create temp file
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.json',
            delete=False,
            prefix='youtube_shorts_backup_'
        ) as f:
            json.dump(data, f, indent=2, default=str)
            temp_path = f.name
        
        # Send file
        with open(temp_path, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=f"youtube_shorts_backup_{user_id}.json",
                caption=(
                    "💾 **Your Data Backup**\n\n"
                    "This file contains:\n"
                    "• Subscriptions\n"
                    "• Favorites\n"
                    "• Queue\n"
                    "• Settings\n\n"
                    "Use `/import` to restore."
                ),
                parse_mode='Markdown'
            )
        
        # Cleanup
        os.unlink(temp_path)
        
        await loading.delete()
        
    except Exception as e:
        await loading.edit_text(f"❌ Export failed: {str(e)}")


async def import_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /import command."""
    await update.message.reply_text(
        "📥 **Import Data**\n\n"
        "Send me a backup JSON file to restore your data.\n\n"
        "⚠️ This will merge with your existing data.",
        parse_mode='Markdown',
        reply_markup=back_button()
    )
    context.user_data['expecting'] = 'import_file'


async def handle_import_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle uploaded JSON file for import."""
    user_id = update.effective_user.id
    document = update.message.document
    
    # Check file type
    if not document.file_name.endswith('.json'):
        await update.message.reply_text(
            "❌ Please send a JSON file.\n\n"
            "The backup file should end with `.json`",
            parse_mode='Markdown'
        )
        return
    
    # Check file size (max 1MB)
    if document.file_size > 1024 * 1024:
        await update.message.reply_text("❌ File too large. Maximum 1MB.")
        return
    
    loading = await update.message.reply_text("📥 Importing your data...")
    
    try:
        # Download file
        file = await document.get_file()
        file_bytes = await file.download_as_bytearray()
        
        # Parse JSON
        data = json.loads(file_bytes.decode('utf-8'))
        
        # Import data
        counts = await import_user_data(user_id, data)
        
        await loading.edit_text(
            f"✅ **Import Complete!**\n\n"
            f"📺 Subscriptions: +{counts['subscriptions']}\n"
            f"⭐ Favorites: +{counts['favorites']}\n"
            f"📥 Queue: +{counts['queue']}\n\n"
            f"Settings have been applied.",
            parse_mode='Markdown',
            reply_markup=back_button()
        )
        
    except json.JSONDecodeError:
        await loading.edit_text(
            "❌ Invalid JSON file. Please check the file format.",
            reply_markup=back_button()
        )
    except Exception as e:
        await loading.edit_text(
            f"❌ Import failed: {str(e)}",
            reply_markup=back_button()
        )
    finally:
        context.user_data.pop('expecting', None)


# Message handler for import files
import_file_handler = MessageHandler(
    filters.Document.MimeType("application/json"),
    handle_import_file
)
