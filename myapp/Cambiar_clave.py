import getpass

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.db import connection

from myapp.permisos import validar_clave


class Command(BaseCommand):
    help = 'Cambia la contraseña de cualquier usuario (por si el administrador principal la olvidó)'

    def handle(self, *args, **options):
        usuario = input('Usuario: ').strip()
        clave = getpass.getpass('Nueva contraseña (no se muestra al escribir): ')
        repetir = getpass.getpass('Repetir contraseña: ')

        errores = validar_clave(clave, usuario)
        if clave != repetir:
            errores.append('Las contraseñas no coinciden.')
        if errores:
            for e in errores:
                self.stdout.write(self.style.ERROR(e))
            return

        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE usuarios SET contrasena = %s WHERE usuario = %s",
                [make_password(clave), usuario],
            )
            if cursor.rowcount == 0:
                self.stdout.write(self.style.ERROR(f'No existe el usuario "{usuario}".'))
                return

        self.stdout.write(self.style.SUCCESS(f'Contraseña de "{usuario}" actualizada.'))