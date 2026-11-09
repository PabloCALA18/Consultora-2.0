import getpass

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.db import IntegrityError, connection

from myapp.permisos import validar_alta


class Command(BaseCommand):
    help = 'Crea la cuenta del administrador PRINCIPAL (solo puede haber una)'

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute("SELECT usuario FROM usuarios WHERE es_principal = 1")
            existente = cursor.fetchone()
        if existente:
            self.stdout.write(self.style.ERROR(
                f'Ya existe un administrador principal ("{existente[0]}"). Solo puede haber uno.'
            ))
            return

        usuario = input('Usuario: ').strip()
        clave = getpass.getpass('Contraseña (no se muestra al escribir): ')
        repetir = getpass.getpass('Repetir contraseña: ')

        errores = validar_alta(usuario, clave, repetir)
        if errores:
            for e in errores:
                self.stdout.write(self.style.ERROR(e))
            return

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO usuarios (usuario, contrasena, rol, es_principal, activo) "
                    "VALUES (%s, %s, 'administrador', 1, 1)",
                    [usuario, make_password(clave)],
                )
        except IntegrityError:
            self.stdout.write(self.style.ERROR(
                f'Ya existe un usuario llamado "{usuario}". Si es tuyo, convertilo en principal en DBeaver con:\n'
                f"UPDATE usuarios SET rol = 'administrador', es_principal = 1 WHERE usuario = '{usuario}';"
            ))
            return

        self.stdout.write(self.style.SUCCESS(f'Administrador principal "{usuario}" creado.'))