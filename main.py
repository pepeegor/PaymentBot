import disnake
from disnake.ext import commands

from bot.data.config import DISCORD_TOKEN
from bot.utils.load_cogs import load_cogs


def main():
    bot = commands.Bot(intents=disnake.Intents.all(), command_prefix='*')
    load_cogs(bot)
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()

# Перетащить бота наверх, создать текст категорию tickets
