"""
Teams adapter package.

Exports the bot handler and command router used by the API route layer.
"""

from src.adapters.teams.bot_handler import WeeklyReportBot
from src.adapters.teams.command_router import CommandRouter

__all__ = ["WeeklyReportBot", "CommandRouter"]
