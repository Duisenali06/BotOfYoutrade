from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_WEBHOOK_SECRET: str
    CLAUDE_API_KEY: str
    DATABASE_URL: str
    WEBHOOK_BASE_URL: str
    ADMIN_CHAT_IDS: str = ""
    ADMIN_DASHBOARD_KEY: str = "change_me"

    MATCHTRADER_LOGIN: str = "demo.ytr777@mail.ru"
    MATCHTRADER_PASSWORD: str = "jAcrex-petqyw-kahke4"
    MATCHTRADER_URL: str = "https://mtr.youtrade.kz/login"
    CHALLENGE_URL: str = "https://youtradeprop.com/challenge-purchase"
    WHATSAPP_NUMBER: str = "77081906251"

    # Botcorp WhatsApp API
    BOTCORP_TOKEN: str = ""
    BOTCORP_CHANNEL_ID: str = ""
    BOTCORP_API_URL: str = "https://chat.botcorp.io/api/apiFromWorkspace"

    @property
    def admin_chat_ids_list(self) -> list[int]:
        if not self.ADMIN_CHAT_IDS:
            return []
        return [int(x.strip()) for x in self.ADMIN_CHAT_IDS.split(",") if x.strip()]


settings = Settings()
