import datetime
import io
import uuid
from copy import deepcopy

import aiosqlite
import disnake
from chat_exporter import chat_exporter
from disnake.ext import commands, tasks
import asyncio
from bot.data.config import DATABASE_URL, CATEGORY_NAME_INFO, CATEGORY_NAME_PAID
from bot.utils.payment import create_payment_link, check_payment


class PaymentModal(disnake.ui.Modal):
    def __init__(self, user_role, price, mod_name, role):
        self.user_role = user_role
        self.price = price
        self.mod_name = mod_name
        self.role = role
        title = "Payment Details RU" if user_role == "Russia" else title = "Payment Details WorldWide"
        components = [
            disnake.ui.TextInput(
                label="Название вашего проекта (как в лаунчере)" if user_role == "Russia" else "Name of Your Project",
                custom_id="project_name",
                style=disnake.TextInputStyle.long,
                required=True
            )
        ]
        super().__init__(title=title, custom_id=f"payment_modal.{price}.{mod_name}.{role}", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        project_name = inter.text_values["project_name"]
        return_url = f"https://discord.com/channels/{inter.guild_id}/{inter.channel_id}"
        url, payment_id = create_payment_link(project_name, self.price, return_url)
        await inter.response.edit_message(
            f"Вот ваша ссылка для оплаты:\n{url}" if self.user_role == "Russia" else f"Here is your payment link:\n{url}",
            embed=None,
            components=disnake.ui.Button(
                label="Проверить статус" if self.user_role == "Russia" else "Check payment status",
                style=disnake.ButtonStyle.green,
                custom_id=f"check_payment.{project_name}.{payment_id}.{self.price}.{self.mod_name}.{self.role}"
            )
        )


class MyBotView(disnake.ui.View):
    def __init__(self, user_role, price: int, mod_name: str, role: str):
        super().__init__()
        self.user_role = user_role
        buy_label = "Купить" if user_role == "Russia" else "Buy"
        info_label = "Информация" if user_role == "Russia" else "Info"
        self.buy_button = disnake.ui.Button(
            label=buy_label,
            style=disnake.ButtonStyle.green,
            custom_id=f"buy_button.{price}.{mod_name}.{role}"
        )
        self.info_button = disnake.ui.Button(
            label=info_label,
            style=disnake.ButtonStyle.blurple,
            custom_id=f"info_button.{price}.{mod_name}.{role}"
        )
        self.add_item(self.buy_button)
        self.add_item(self.info_button)


class BotCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.channel_check.start()

    @commands.slash_command(name="payment")
    @commands.has_role("Owner")
    async def payment(
            self,
            inter: disnake.ApplicationCommandInteraction,
            price: int = commands.Param(),
            mod_name: str = commands.Param(),
            role: str = commands.Param()
    ):
        await inter.response.defer()
        await inter.send('.', delete_after=0)
        user_role = "WorldWide" if "WorldWide" in [role.name for role in inter.author.roles] else "Russia"
        does_role_exist = True if role in [role.name for role in inter.guild.roles] else False
        if does_role_exist:
            view = MyBotView(user_role=user_role, price=price, mod_name=mod_name, role=role)
            embed = disnake.Embed(title="Выбор действия" if user_role == "Russia" else "Choose an action",
                                  description="Выберите один из вариантов ниже" if user_role == "Russia" else "Please choose one of the options below",
                                  color=disnake.Color.blue())
            await inter.channel.send(embed=embed, view=view)
        else:
            await inter.channel.send("Роль, которую вы ввели, не существует.", delete_after=10)

    @commands.slash_command(name="remove")
    @commands.has_role("Owner")
    async def remove(self, inter: disnake.ApplicationCommandInteraction):

        if inter.channel.name.startswith("ticket"):
            await inter.response.defer(ephemeral=True)

            transcript = await chat_exporter.export(
                inter.channel,
                limit=200,
                tz_info="Europe/Moscow",
                military_time=True,
                bot=self.bot,
            )
            if transcript is None:
                await inter.edit_original_response(content="Не удалось получить транскрипт чата.")
                return

            transcript_file = disnake.File(
                io.BytesIO(transcript.encode('utf-8')),
                filename=f"transcript-{inter.channel.name}.html"
            )

            members = inter.channel.members
            for member in members:
                if member.bot:
                    continue
                try:
                    file = deepcopy(transcript_file)
                    if "WorldWide" in [role.name for role in member.roles]:
                        content = f"Your order #{inter.channel.name}"
                    else:
                        content = f"Ваш заказ #{inter.channel.name}"
                    await member.send(content=content, file=file)
                except disnake.HTTPException as e:
                    print(f"Не удалось отправить сообщение пользователю {member.display_name}: {e}")

            await asyncio.sleep(5)
            await inter.channel.delete(reason="Ticket got Deleted!")

        elif inter.channel.name.startswith("info"):
            await inter.channel.delete()
        else:
            return await inter.response.send_message("Этот канал не является тикетом.", ephemeral=True)

    @tasks.loop(hours=12)
    async def channel_check(self):
        await self.bot.wait_until_ready()
        now = datetime.datetime.utcnow()
        for guild in self.bot.guilds:
            for channel in guild.text_channels:
                if channel.name.startswith("ticket"):
                    try:
                        last_message = await channel.history(limit=1).flatten()
                        if last_message:
                            last_message_time = last_message[0].created_at.replace(tzinfo=None)
                            if (now - last_message_time).days >= 3:
                                await self.remove_channel(channel)
                    except Exception as e:
                        print(f"Ошибка при проверке канала {channel.name}: {e}")
                elif channel.name.startswith("info"):
                    try:
                        last_message = await channel.history(limit=1).flatten()
                        if last_message:
                            last_message_time = last_message[0].created_at.replace(tzinfo=None)
                            if (now - last_message_time).seconds >= 86400:
                                await channel.delete()
                    except Exception as e:
                        print(f"Ошибка при проверке канала {channel.name}: {e}")

    async def remove_channel(self, channel):
        if channel is None or not channel.name.startswith("ticket"):
            print("Канал не найден или не является тикетом.")
            return
        transcript = await chat_exporter.export(
            channel,
            limit=200,
            tz_info="Europe/Moscow",
            military_time=True,
            bot=self.bot,
        )
        if transcript is None:
            return

        transcript_file = disnake.File(
            io.BytesIO(transcript.encode('utf-8')),
            filename=f"transcript-{channel.name}.html"
        )

        members = channel.members
        for member in members:
            if member.bot:
                continue
            try:
                file = deepcopy(transcript_file)
                if "WorldWide" in [role.name for role in member.roles]:
                    content = f"Your order #{channel.name}"
                else:
                    content = f"Ваш заказ #{channel.name}"
                member.send(content=content, file=file)

            except disnake.HTTPException as e:
                print(f"Не удалось отправить сообщение пользователю {member.display_name}: {e}")

        await asyncio.sleep(5)
        await channel.delete(reason="Ticket got Deleted!")

    @commands.Cog.listener("on_button_click")
    async def buy_callback(self, inter: disnake.MessageInteraction):
        user_role = "WorldWide" if "WorldWide" in [role.name for role in inter.author.roles] else "Russia"
        if "buy_button" not in inter.component.custom_id and "info_button" not in inter.component.custom_id:
            return
        elif "buy_button" in inter.component.custom_id:
            payment = inter.component.custom_id.split(".")
            price = payment[1]
            mod_name = payment[2]
            role = payment[3]
            if user_role == "Russia":
                embed = disnake.Embed(title="📜 Подтверждение соглашений",
                                      description="Перед покупкой вы должны согласиться с условиями предоставления продуктов и услуг:",
                                      color=disnake.Color.blue())

                embed.add_field(name="Я соглашаюсь с пользовательским соглашением Modfactory",
                                value="[Прочитать и согласиться](https://discord.com/channels/1116332077772722186/1211731008269975562)",
                                inline=False)

                embed.add_field(name="Я соглашаюсь с правила оказания услуг Modfactory",
                                value="[Прочитать и согласиться](https://discord.com/channels/1116332077772722186/1211732683923656724)",
                                inline=False)

                embed.add_field(name="Я соглашаюсь с правилами торговой площадки Modfactory",
                                value="[Прочитать и согласиться](https://discord.com/channels/1116332077772722186/1211732785098661951)",
                                inline=False)

                components = [
                    disnake.ui.Button(label="Согласен", style=disnake.ButtonStyle.green,
                                      custom_id=f"yes_1.{price}.{mod_name}.{role}"),
                    disnake.ui.Button(label="Не согласен", style=disnake.ButtonStyle.red, custom_id="no")
                ]
            else:
                embed = disnake.Embed(title="📜 Confirmation of agreements",
                                      description="You must agree with Modfactory Terms and Rules before you offer anything:",
                                      color=disnake.Color.blue())

                embed.add_field(name="Modfactory-user-licence",
                                value="[Read and agree](https://discord.com/channels/1116332077772722186/1211733305410461826)",
                                inline=False)

                embed.add_field(name="Modfactory-service-rules",
                                value="[Read and agree](https://discord.com/channels/1116332077772722186/1211733505675894804)",
                                inline=False)

                embed.add_field(name="Modfactory-marketplace-rules",
                                value="[Read and agree](https://discord.com/channels/1116332077772722186/1211733571434455100)",
                                inline=False)

                components = [
                    disnake.ui.Button(label="I agree", style=disnake.ButtonStyle.green,
                                      custom_id=f"yes_1.{price}.{mod_name}.{role}"),
                    disnake.ui.Button(label="No", style=disnake.ButtonStyle.red, custom_id="no")
                ]
            await inter.response.send_message(embed=embed, components=components, ephemeral=True)
        else:
            payment = inter.component.custom_id.split(".")
            mod_name = payment[2]
            category = disnake.utils.get(inter.guild.categories, name=CATEGORY_NAME_INFO)
            overwrites = {
                inter.guild.default_role: disnake.PermissionOverwrite(read_messages=False),
                inter.author: disnake.PermissionOverwrite(read_messages=True),
                disnake.utils.get(inter.guild.roles, name="Owner"): disnake.PermissionOverwrite(
                    read_messages=True,
                )
            }
            name = f"info-{inter.author.name}-{mod_name}"
            print(name)
            if name in [str(channel) for channel in inter.guild.text_channels]:
                if user_role == "Russia":
                    text = "Ваш канал по вопросам уже открыт."
                else:
                    text = "Your question channel is already open."
                await inter.response.send_message(text, ephemeral=True)
            else:
                ticket_channel = await inter.guild.create_text_channel(
                    name=name,
                    overwrites=overwrites,
                    category=category
                )
                if user_role == "Russia":
                    await ticket_channel.send("Здравствуйте, здесь вы можете задавать свои вопросы.")
                    await inter.response.send_message("Ваш канал по вопросам открыт.", ephemeral=True)
                else:
                    await ticket_channel.send("Hello, you can ask your questions here.")
                    await inter.response.send_message("Your question channel is open.", ephemeral=True)

    @commands.Cog.listener("on_button_click")
    async def yes_callback(self, inter: disnake.MessageInteraction):
        user_role = "WorldWide" if "WorldWide" in [role.name for role in inter.author.roles] else "Russia"
        if "yes_1" not in inter.component.custom_id and "no" not in inter.component.custom_id:
            return
        elif "yes_1" in inter.component.custom_id:
            payment = inter.component.custom_id.split(".")
            price = payment[1]
            mod_name = payment[2]
            role = payment[3]
            modal = PaymentModal(user_role, price, mod_name, role)
            await inter.response.send_modal(modal)
        elif "no" in inter.component.custom_id:
            title = "Для покупки вы должны быть согласны с условиями." if user_role == "Russia" else "For the purchase, you must agree to the terms."
            embed = disnake.Embed(title=title, color=disnake.Color.red())
            await inter.response.send_message(embed=embed, ephemeral=True, delete_after=60)

    @commands.Cog.listener("on_button_click")
    async def payment_callback(self, inter: disnake.MessageInteraction):
        user_role = "WorldWide" if "WorldWide" in [role.name for role in inter.author.roles] else "Russia"
        if "check_payment" not in inter.component.custom_id:
            return
        payment = inter.component.custom_id.split(".")
        project_name = payment[1]
        payment_id = payment[2]
        price = payment[3]
        mod_name = payment[4]
        role = payment[5]
        if check_payment(payment_id):
            category = disnake.utils.get(inter.guild.categories, name=CATEGORY_NAME_PAID)
            overwrites = {
                inter.guild.default_role: disnake.PermissionOverwrite(read_messages=False),
                inter.author: disnake.PermissionOverwrite(read_messages=True),
                disnake.utils.get(inter.guild.roles, name="Owner"): disnake.PermissionOverwrite(
                    read_messages=True,
                )
            }
            name = f"ticket-{inter.author.name}-{mod_name}"
            if name in [str(channel) for channel in inter.guild.text_channels]:
                if user_role == "Russia":
                    text = "Ваш тикет уже открыт."
                else:
                    text = "Your ticket is already open."
                await inter.response.send_message(text, ephemeral=True)
            else:
                ticket_channel = await inter.guild.create_text_channel(
                    name=name,
                    overwrites=overwrites,
                    category=category
                )
                print(role)
                role = disnake.utils.get(inter.guild.roles, name=role)
                await inter.author.add_roles(role)
                mod_exists = await self.check_mode(mod_name)
                if mod_exists:
                    key = str(uuid.uuid4())
                    if user_role == "Russia":
                        ticket_text = f"Оплата прошла успешно. Информация о проекте {project_name}\nМод: {mod_name}\nКлюч: ||{key}||\nВам была выдана роль {role.mention}\nОжидайте связи модератора."
                        response_text = f"Канал для обсуждения проекта '{project_name}' создан."
                    else:
                        ticket_text = f"Payment was successful. Project information: {project_name}\nMod name: {mod_name}\nKey: ||{key}||\nYou have been assigned the role {role.mention}\nPlease wait for the moderator to contact you."
                        response_text = f"Channel for discussing the project '{project_name}' has been created."
                    await ticket_channel.send(ticket_text)
                    await self.add_user(modname=mod_name, projectname=project_name, key=key)
                    await inter.response.edit_message(response_text, components=None)
                else:
                    if user_role == "Russia":
                        ticket_text = f"Оплата прошла успешно. Информация о проекте {project_name}\nМод: {mod_name}\nВам была выдана роль {role.mention}\nОжидайте связи модератора."
                        response_text = f"Канал для обсуждения проекта '{project_name}' создан."
                    else:
                        ticket_text = f"Payment was successful. Project information: {project_name}\nMod name: {mod_name}\nYou have been assigned the role {role.mention}\nPlease wait for the moderator to contact you."
                        response_text = f"Channel for discussing the project '{project_name}' has been created."
                    await ticket_channel.send(ticket_text)
                    await inter.response.edit_message(response_text, components=None)
        else:
            if user_role == "Russia":
                text = "Оплата ещё не прошла."
            else:
                text = "Payment has not yet been processed."
            await inter.response.send_message(text, ephemeral=True, delete_after=10)

    @staticmethod
    async def add_user(modname, projectname, key):
        async with aiosqlite.connect(DATABASE_URL) as db:
            await db.execute('INSERT INTO Keys (modname, projectname, key) VALUES (?, ?, ?)', (modname, projectname, key, ))
            await db.commit()

    @staticmethod
    async def check_mode(modname):
        async with aiosqlite.connect(DATABASE_URL) as db:
            mod_exists = await db.execute('SELECT EXISTS(SELECT 1 FROM Mods WHERE modname = ?)', (modname,))
            mod_exists = await mod_exists.fetchone()
        return bool(mod_exists[0])


def setup(bot: commands.Bot):
    bot.add_cog(BotCog(bot))
