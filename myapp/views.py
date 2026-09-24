from functools import wraps

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.hashers import check_password
from django.db import connection


def dictfetchall(cursor):
    """Convierte el resultado de un cursor en una lista de diccionarios."""
    columnas = [col[0] for col in cursor.description]
    return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]


def login_requerido(vista):
    """
    Reemplazo casero de @login_required: en vez de mirar request.user
    (sistema de Django), mira si hay un admin guardado en la sesión.
    """
    @wraps(vista)
    def envoltorio(request, *args, **kwargs):
        if 'admin_id' not in request.session:
            return redirect('login')
        return vista(request, *args, **kwargs)
    return envoltorio


def home_publico(request):
    """
    Página de inicio pública (institucional). No requiere login.
    Muestra proyectos vendidos y empresas clientes como vidriera,
    con un botón que lleva al login del personal.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM proyecto")
        total_proyectos = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM empresa_cliente")
        total_empresas = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM consultor")
        total_consultores = cursor.fetchone()[0]

        cursor.execute(
            "SELECT descripcion, coste FROM proyecto ORDER BY id DESC LIMIT 6"
        )
        proyectos_destacados = dictfetchall(cursor)

        cursor.execute(
            "SELECT nombre FROM empresa_cliente ORDER BY id DESC LIMIT 12"
        )
        empresas_clientes = dictfetchall(cursor)

    return render(request, 'myapp/home.html', {
        'total_proyectos': total_proyectos,
        'total_empresas': total_empresas,
        'total_consultores': total_consultores,
        'proyectos_destacados': proyectos_destacados,
        'empresas_clientes': empresas_clientes,
    })

# ---------- LOGIN / LOGOUT ----------

def login_view(request):
    if 'admin_id' in request.session:
        return redirect('inicio')

    if request.method == 'POST':
        usuario = request.POST.get('username')
        contrasena = request.POST.get('password')

        # --- ACCESO TEMPORAL DE PRUEBA, SIN TOCAR LA BASE ---
        # Sirve para probar el resto del sistema mientras el login real
        # contra la base todavía no funciona. BORRAR este bloque después.
        if usuario == 'admin' and contrasena == 'admin123':
            request.session['admin_id'] = 0
            request.session['admin_usuario'] = 'admin'
            return redirect('inicio')
        # --- FIN DEL ACCESO TEMPORAL ---

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, usuario, contrasena FROM administrador WHERE usuario = %s",
                [usuario],
            )
            fila = dictfetchall(cursor)

        if fila and check_password(contrasena, fila[0]['contrasena']):
            request.session['admin_id'] = fila[0]['id']
            request.session['admin_usuario'] = fila[0]['usuario']
            return redirect('inicio')

        messages.error(request, 'Usuario o contraseña incorrectos.')

    return render(request, 'myapp/login.html')


def logout_view(request):
    request.session.flush()
    return redirect('login')


# ---------- INICIO ----------

@login_requerido
def inicio(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM consultor")
        total_consultores = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM empresa_cliente")
        total_empresas = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM proyecto")
        total_proyectos = cursor.fetchone()[0]

    return render(request, 'myapp/inicio.html', {
        'total_consultores': total_consultores,
        'total_empresas': total_empresas,
        'total_proyectos': total_proyectos,
    })


# ---------- CONSULTORES ----------

@login_requerido
def consultores(request):
    if request.method == 'POST':
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO consultor (codigo_empleado, nombre, sueldo, categoria_id, jefe_id)
                VALUES (%s, %s, %s, %s, %s)
                """,
                [
                    request.POST.get('codigo_empleado'),
                    request.POST.get('nombre'),
                    request.POST.get('sueldo'),
                    request.POST.get('categoria'),
                    request.POST.get('jefe') or None,
                ],
            )
        messages.success(request, 'Consultor cargado correctamente.')
        return redirect('consultores')

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.codigo_empleado, c.nombre, c.sueldo,
                   cat.nombre AS categoria_nombre,
                   jefe.nombre AS jefe_nombre
            FROM consultor c
            JOIN categoria_profesional cat ON c.categoria_id = cat.id
            LEFT JOIN consultor jefe ON c.jefe_id = jefe.codigo_empleado
            """
        )
        lista_consultores = dictfetchall(cursor)

        cursor.execute("SELECT id, nombre FROM categoria_profesional")
        categorias = dictfetchall(cursor)

        cursor.execute("SELECT codigo_empleado, nombre FROM consultor")
        posibles_jefes = dictfetchall(cursor)

    return render(request, 'myapp/consultores.html', {
        'consultores': lista_consultores,
        'categorias': categorias,
        'posibles_jefes': posibles_jefes,
    })


@login_requerido
def eliminar_consultor(request, pk):
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM consultor WHERE codigo_empleado = %s", [pk])
    messages.success(request, 'Consultor eliminado.')
    return redirect('consultores')


# ---------- EMPRESAS ----------

@login_requerido
def empresas(request):
    if request.method == 'POST':
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO empresa_cliente (nombre, direccion, cif) VALUES (%s, %s, %s)",
                [request.POST.get('nombre'), request.POST.get('direccion'), request.POST.get('cif')],
            )
            empresa_id = cursor.lastrowid
            telefono = request.POST.get('telefono')
            if telefono:
                cursor.execute(
                    "INSERT INTO telefono (numero, empresa_id) VALUES (%s, %s)",
                    [telefono, empresa_id],
                )
        messages.success(request, 'Empresa cargada correctamente.')
        return redirect('empresas')

    with connection.cursor() as cursor:
        cursor.execute("SELECT id, nombre, direccion, cif FROM empresa_cliente")
        lista_empresas = dictfetchall(cursor)

        cursor.execute("SELECT numero, empresa_id FROM telefono")
        telefonos = dictfetchall(cursor)

    telefonos_por_empresa = {}
    for t in telefonos:
        telefonos_por_empresa.setdefault(t['empresa_id'], []).append(t['numero'])

    for e in lista_empresas:
        e['telefonos'] = telefonos_por_empresa.get(e['id'], [])

    return render(request, 'myapp/empresas.html', {'empresas': lista_empresas})


@login_requerido
def eliminar_empresa(request, pk):
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM telefono WHERE empresa_id = %s", [pk])
        cursor.execute("DELETE FROM empresa_cliente WHERE id = %s", [pk])
    messages.success(request, 'Empresa eliminada.')
    return redirect('empresas')


# ---------- PROYECTOS ----------

@login_requerido
def proyectos(request):
    if request.method == 'POST':
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO proyecto (descripcion, coste) VALUES (%s, %s)",
                [request.POST.get('descripcion'), request.POST.get('coste')],
            )
        messages.success(request, 'Proyecto cargado correctamente.')
        return redirect('proyectos')

    with connection.cursor() as cursor:
        cursor.execute("SELECT id, descripcion, coste FROM proyecto")
        lista_proyectos = dictfetchall(cursor)

    return render(request, 'myapp/proyectos.html', {'proyectos': lista_proyectos})


@login_requerido
def eliminar_proyecto(request, pk):
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM proyecto WHERE id = %s", [pk])
    messages.success(request, 'Proyecto eliminado.')
    return redirect('proyectos')


# ---------- SOLO DEBUG: ver el contenido crudo de administrador ----------
# OJO: esta vista no pide login y muestra los hashes guardados.
# Es únicamente para que verifiques mientras desarrollás.
# Borrala (y su ruta en urls.py) antes de entregarle el proyecto al cliente.

def ver_admins(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, usuario, contrasena FROM administrador")
        admins = dictfetchall(cursor)
    return render(request, 'myapp/admins.html', {'admins': admins})