from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Описание вашей команды"

    def add_arguments(self, parser):
        # Добавление аргументов для команды (опционально)
        parser.add_argument("my_arg", type=str, help="Описание аргумента")
        parser.add_argument(
            "--option", type=str, help="Описание опционального аргумента"
        )

    def handle(self, *args, **options):
        # Логика вашей команды
        arg_value = options["my_arg"]
        option_value = options.get("option", "default_value")

        self.stdout.write(f"Выполняется команда с аргументом: {arg_value}")
        self.stdout.write(f"Опциональный аргумент: {option_value}")

        # Здесь ваша кастомная логика
        self.stdout.write(self.style.SUCCESS("Команда успешно выполнена!"))
