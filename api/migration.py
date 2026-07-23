from alembic import command
from alembic.config import Config
from pathlib import Path

ALEMBIC_INI = Path(__file__).with_name("alembic.ini")

def run_auto_migrations(msg: str = "autogenerate"):
    cfg = Config(str(ALEMBIC_INI))

    # 1. Догоняем БД до текущей головы
    command.upgrade(cfg, "head")      # ← здесь проблема больше не возникнет

    # 2. Пробуем создать новый revision
    rev_id = command.revision(
        cfg,
        message=msg,
        autogenerate=True,
        sql=False,
    )

    # 3. Если создан новый файл, применяем его
    if rev_id:
        print(f"Создана миграция {rev_id}. Применяем…")
        command.upgrade(cfg, "head")
    else:
        print("Схема БД уже актуальна — миграций не требуется.")