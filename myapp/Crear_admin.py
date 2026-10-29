import getpass

from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, connection

from myapp.permisos import ROLES


class Command(BaseCommand):
    help = 'Crea un usuario en la tabla administrador con su rol y la contraseña ya hasheada'

    def handle(self, *args, **options):
        usuario = input('Usuario: ').strip()
        print('Roles disponibles: ' + ', '.join(ROLES))
        rol = input('Rol: ').strip()

        if rol not in ROLES:
            self.stdout.write(self.style.ERROR(
                f'Rol inválido. Tiene que ser uno de: {", ".join(ROLES)}'
            ))
            return

        clave = getpass.getpass('Contraseña (no se muestra al escribir): ')

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO administrador (usuario, contrasena, rol) VALUES (%s, %s, %s)",
                    [usuario, make_password(clave), rol],
                )
        except IntegrityError:
            self.stdout.write(self.style.ERROR(
                f'Ya existe un usuario llamado "{usuario}". Elegí otro nombre.'
            ))
            return

        self.stdout.write(self.style.SUCCESS(
            f'Usuario "{usuario}" creado con rol {ROLES[rol]}.'
        ))