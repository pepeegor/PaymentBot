import os
import yookassa


from dotenv import (
    load_dotenv,
    find_dotenv
)


load_dotenv(find_dotenv())
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
API_TOKEN = os.getenv("API_TOKEN")
SHOP_ID = int(os.getenv("SHOP_ID"))
CATEGORY_NAME_INFO = os.getenv("CATEGORY_NAME_INFO")
CATEGORY_NAME_PAID = os.getenv("CATEGORY_NAME_PAID")
DATABASE_URL = os.getenv("DATABASE_URL")
yookassa.Configuration.secret_key = API_TOKEN
yookassa.Configuration.account_id = SHOP_ID