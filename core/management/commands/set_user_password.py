from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Set a user password non-interactively'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str)
        parser.add_argument('password', type=str)

    def handle(self, *args, **options):
        User = get_user_model()
        try:
            user = User.objects.get(username=options['username'])
        except User.DoesNotExist:
            raise CommandError(f"User '{options['username']}' does not exist")

        user.set_password(options['password'])
        user.save()
        self.stdout.write(self.style.SUCCESS(f"Password changed for {options['username']}"))
