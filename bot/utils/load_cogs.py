import os
from disnake.ext import commands


def load_cogs(bot: commands.Bot):
    bot_dir = 'bot'
    cogs_dir = 'cogs'
    cogs_folder = os.path.join(bot_dir, cogs_dir)

    for name in os.listdir(cogs_folder):
        if name.endswith(".py") and os.path.isfile(os.path.join(cogs_folder, name)):
            bot.load_extension(f"{bot_dir}.{cogs_dir}.{name[:-3]}")
