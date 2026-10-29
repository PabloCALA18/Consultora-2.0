"""
Roles, permisos y usuarios de prueba del sistema.

PARA CONECTAR EL LOGIN CON LA BASE DE DATOS (más adelante):
1. Agregar la columna rol a la tabla administrador (en DBeaver):
       ALTER TABLE administrador
       ADD COLUMN rol VARCHAR(20) NOT NULL DEFAULT 'operario';
2. Cargar los usuarios con su rol ('administrador', 'rrhh' u 'operario'),
   con la contraseña hasheada (make_password).
3. Cambiar USAR_BASE_DE_DATOS a True. Desde ese momento USUARIOS_DEMO
   deja de usarse y se puede borrar.
"""

USAR_BASE_DE_DATOS = False

# Nombre "lindo" de cada rol, para mostrar en pantalla.
ROLES = {
    'administrador': 'Administrador',
    'rrhh': 'Recursos Humanos',
    'operario': 'Operario',
}

# Qué roles pueden AGREGAR / ELIMINAR en cada sección.
# Todos los roles logueados pueden VER todas las secciones.
PERMISOS_ESCRITURA = {
    'consultores': {'administrador', 'rrhh'},
    'empresas': {'administrador'},
    'proyectos': {'administrador'},
}

# Usuarios de prueba (SOLO mientras USAR_BASE_DE_DATOS sea False).
USUARIOS_DEMO = {
    'admin':    {'id': 1, 'contrasena': 'admin123',    'rol': 'administrador'},
    'rrhh':     {'id': 2, 'contrasena': 'rrhh123',     'rol': 'rrhh'},
    'operario': {'id': 3, 'contrasena': 'operario123', 'rol': 'operario'},
}


def puede_modificar(rol, seccion):
    return rol in PERMISOS_ESCRITURA.get(seccion, set())


def contexto_usuario(request):
    """Datos del usuario logueado y sus permisos, listos para los templates."""
    rol = request.session.get('rol')
    return {
        'admin_usuario': request.session.get('admin_usuario'),
        'rol': rol,
        'rol_nombre': ROLES.get(rol, ''),
        'puede_modificar_consultores': puede_modificar(rol, 'consultores'),
        'puede_modificar_empresas': puede_modificar(rol, 'empresas'),
        'puede_modificar_proyectos': puede_modificar(rol, 'proyectos'),
    }