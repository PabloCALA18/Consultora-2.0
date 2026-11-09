from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.staticfiles import finders
from django.db import IntegrityError, connection, transaction
from django.db.utils import ProgrammingError
from django.http import Http404
from django.shortcuts import redirect, render
from django.templatetags.static import static

from .fundadores import FUNDADORES
from .permisos import (
    PERMISOS,
    REGISTRO_REQUIERE_APROBACION,
    ROLES,
    contexto_usuario,
    permisos_efectivos,
    tiene_permiso,
    usuario_actual,
    validar_alta,
    validar_clave,
)


# ---------- HELPERS ----------

def dictfetchall(cursor):
    """Convierte el resultado de un cursor en una lista de diccionarios."""
    columnas = [col[0] for col in cursor.description]
    return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]


def renderizar(request, plantilla, datos=None):
    """
    render() que además agrega usuario, rol y permisos al contexto,
    para que los templates sepan qué botones mostrar.
    """
    contexto = contexto_usuario(request)
    contexto.update(datos or {})
    return render(request, plantilla, contexto)


def login_requerido(vista):
    """Exige un usuario logueado (leído de la base). Si la cuenta se desactivó o borró, cierra la sesión."""
    @wraps(vista)
    def envoltorio(request, *args, **kwargs):
        if usuario_actual(request) is None:
            request.session.flush()
            return redirect('login')
        return vista(request, *args, **kwargs)
    return envoltorio


def requiere(permiso, volver_a='inicio'):
    """Deja pasar solo a quien tenga `permiso` (ver permisos.py). Si no, vuelve a `volver_a`."""
    def decorador(vista):
        @wraps(vista)
        def envoltorio(request, *args, **kwargs):
            if not tiene_permiso(request, permiso):
                messages.error(request, 'Tu usuario no tiene permiso para esto.')
                return redirect(volver_a)
            return vista(request, *args, **kwargs)
        return envoltorio
    return decorador


def permiso_requerido(seccion, solo_post=False):
    """
    Deja pasar solo a los roles que pueden modificar `seccion`.
    - solo_post=False: se bloquea siempre (por ejemplo, eliminar).
    - solo_post=True: se bloquea solo al enviar el formulario (POST);
      ver la lista (GET) queda permitido para todos los roles.
    """
    def decorador(vista):
        @wraps(vista)
        def envoltorio(request, *args, **kwargs):
            es_escritura = (request.method == 'POST') if solo_post else True
            if es_escritura and not tiene_permiso(request, f'{seccion}.modificar'):
                messages.error(request, 'Tu usuario no tiene permiso para realizar esta acción.')
                return redirect(seccion)
            return vista(request, *args, **kwargs)
        return envoltorio
    return decorador


# ---------- PÁGINA PÚBLICA ----------

def _estado_venta(fecha_inicio, fecha_fin):
    hoy = date.today()
    if fecha_fin and fecha_fin < hoy:
        return 'Finalizado'
    if fecha_inicio and fecha_inicio > hoy:
        return 'Próximo'
    return 'En curso'


def home_publico(request):
    """
    Página institucional, sin login. Es una vidriera: no muestra costes
    ni precios, solo proyectos, clientes y actividad reciente.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM proyecto")
        total_proyectos = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM empresa_cliente")
        total_empresas = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM consultor")
        total_consultores = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM venta")
        total_ventas = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT p.id, p.descripcion,
                   COUNT(v.id) AS veces_vendido,
                   MIN(v.fecha_inicio) AS primer_inicio,
                   MAX(v.fecha_fin) AS ultimo_fin
            FROM proyecto p
            LEFT JOIN venta v ON v.proyecto_id = p.id
            GROUP BY p.id, p.descripcion
            ORDER BY veces_vendido DESC, p.id DESC
            LIMIT 6
            """
        )
        proyectos_destacados = dictfetchall(cursor)

        cursor.execute(
            """
            SELECT e.id, e.nombre, e.direccion,
                   COUNT(v.id) AS proyectos_contratados
            FROM empresa_cliente e
            LEFT JOIN venta v ON v.empresa_id = e.id
            GROUP BY e.id, e.nombre, e.direccion
            ORDER BY proyectos_contratados DESC, e.nombre
            LIMIT 12
            """
        )
        empresas_clientes = dictfetchall(cursor)

        cursor.execute(
            """
            SELECT e.nombre AS empresa, p.descripcion AS proyecto,
                   v.fecha_inicio, v.fecha_fin
            FROM venta v
            JOIN empresa_cliente e ON v.empresa_id = e.id
            JOIN proyecto p ON v.proyecto_id = p.id
            ORDER BY v.fecha_inicio DESC
            LIMIT 8
            """
        )
        ventas_recientes = dictfetchall(cursor)

        cursor.execute(
            """
            SELECT cat.nombre, COUNT(c.codigo_empleado) AS cantidad
            FROM categoria_profesional cat
            LEFT JOIN consultor c ON c.categoria_id = cat.id
            GROUP BY cat.id, cat.nombre
            ORDER BY cat.id
            """
        )
        categorias_equipo = dictfetchall(cursor)

    for v in ventas_recientes:
        v['estado'] = _estado_venta(v['fecha_inicio'], v['fecha_fin'])

    return renderizar(request, 'myapp/home.html', {
        'total_proyectos': total_proyectos,
        'total_empresas': total_empresas,
        'total_consultores': total_consultores,
        'total_ventas': total_ventas,
        'proyectos_destacados': proyectos_destacados,
        'empresas_clientes': empresas_clientes,
        'ventas_recientes': ventas_recientes,
        'categorias_equipo': categorias_equipo,
        'fundadores': _fundadores(),
    })


# ---------- QUIÉNES SOMOS (fundadores) ----------

EXTENSIONES_FOTO = ('jpg', 'jpeg', 'png', 'webp')


def _foto_de(slug):
    """URL de la foto si existe myapp/static/myapp/img/fundadores/<slug>.<ext>, o None."""
    for extension in EXTENSIONES_FOTO:
        ruta = f'myapp/img/fundadores/{slug}.{extension}'
        if finders.find(ruta):
            return static(ruta)
    return None


def _fundadores():
    return [dict(f, foto=_foto_de(f['slug'])) for f in FUNDADORES]


def fundador_detalle(request, slug):
    """Página pública con la biografía completa y los proyectos de un fundador."""
    fundadores = _fundadores()
    fundador = next((f for f in fundadores if f['slug'] == slug), None)
    if fundador is None:
        raise Http404('Fundador no encontrado')

    return renderizar(request, 'myapp/fundador_detalle.html', {
        'fundador': fundador,
        'otros_fundadores': [f for f in fundadores if f['slug'] != slug],
    })


# ---------- LOGIN / REGISTRO / LOGOUT (usuarios guardados en la base) ----------

def _tabla_usuarios_faltante(error):
    return bool(error.args) and error.args[0] == 1146       # "la tabla no existe"


def login_view(request):
    if usuario_actual(request):
        return redirect('inicio')

    if request.method == 'POST':
        usuario = request.POST.get('username', '').strip()
        clave = request.POST.get('password', '')
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, contrasena, activo FROM usuarios WHERE usuario = %s", [usuario]
                )
                fila = cursor.fetchone()
        except ProgrammingError as error:
            if not _tabla_usuarios_faltante(error):
                raise
            messages.error(request, 'Falta crear la tabla de usuarios: ejecutá crear_usuarios.sql en DBeaver.')
            return renderizar(request, 'myapp/login.html')

        if fila and check_password(clave, fila[1]):
            if not fila[2]:
                messages.error(request, 'Tu cuenta está pendiente de aprobación o fue desactivada.')
            else:
                request.session.cycle_key()
                request.session['usuario_id'] = fila[0]
                return redirect('inicio')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos.')

    return renderizar(request, 'myapp/login.html')


def registro_view(request):
    """Cualquiera puede crear una cuenta; siempre queda con el rol Operario (solo lectura)."""
    if usuario_actual(request):
        return redirect('inicio')

    usuario = ''
    if request.method == 'POST':
        usuario = request.POST.get('usuario', '').strip()
        errores = validar_alta(usuario, request.POST.get('contrasena', ''), request.POST.get('repetir', ''))

        if not errores:
            activo = 0 if REGISTRO_REQUIERE_APROBACION else 1
            try:
                with connection.cursor() as cursor:
                    # El rol va fijo en el SQL: nunca se toma de lo que manda el formulario.
                    cursor.execute(
                        "INSERT INTO usuarios (usuario, contrasena, rol, activo) "
                        "VALUES (%s, %s, 'operario', %s)",
                        [usuario, make_password(request.POST.get('contrasena')), activo],
                    )
                    nuevo_id = cursor.lastrowid
            except IntegrityError:
                errores.append('Ese nombre de usuario ya está en uso.')
            except ProgrammingError as error:
                if not _tabla_usuarios_faltante(error):
                    raise
                errores.append('Falta crear la tabla de usuarios: ejecutá crear_usuarios.sql en DBeaver.')
            else:
                if REGISTRO_REQUIERE_APROBACION:
                    messages.success(request, 'Cuenta creada. Un administrador tiene que aprobarla antes de que puedas ingresar.')
                    return redirect('login')
                request.session.cycle_key()
                request.session['usuario_id'] = nuevo_id
                messages.success(request, '¡Cuenta creada! Ya podés ver el sistema.')
                return redirect('inicio')

        for e in errores:
            messages.error(request, e)

    return renderizar(request, 'myapp/registro.html', {
        'usuario_escrito': usuario,
        'requiere_aprobacion': REGISTRO_REQUIERE_APROBACION,
    })


def logout_view(request):
    request.session.flush()
    return redirect('home')


# ---------- CONTRATACIONES (consulta compartida) ----------

def _ventas(cursor, filtro='', parametros=None):
    """
    Contrataciones (tabla venta) con los nombres de empresa, proyecto y consultor.
    `filtro` es un WHERE escrito por nosotros (nunca texto del usuario);
    los valores van siempre en `parametros`.
    """
    cursor.execute(
        f"""
        SELECT v.id, v.precio, v.fecha_inicio, v.fecha_fin,
               p.id AS proyecto_id, p.descripcion AS proyecto, p.coste,
               e.id AS empresa_id, e.nombre AS empresa,
               c.codigo_empleado AS consultor_id, c.nombre AS consultor
        FROM venta v
        JOIN proyecto p ON v.proyecto_id = p.id
        JOIN empresa_cliente e ON v.empresa_id = e.id
        JOIN consultor c ON v.consultor_id = c.codigo_empleado
        {filtro}
        ORDER BY v.fecha_inicio DESC, v.id DESC
        """,
        parametros or [],
    )
    ventas = dictfetchall(cursor)
    for v in ventas:
        v['estado'] = _estado_venta(v['fecha_inicio'], v['fecha_fin'])
    return ventas


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

        ventas = _ventas(cursor)

        cursor.execute(
            """
            SELECT p.id, p.descripcion, COUNT(v.id) AS veces_vendido
            FROM proyecto p
            JOIN venta v ON v.proyecto_id = p.id
            GROUP BY p.id, p.descripcion
            ORDER BY veces_vendido DESC, p.id
            LIMIT 5
            """
        )
        proyectos_top = dictfetchall(cursor)

        cursor.execute(
            """
            SELECT e.id, e.nombre, COUNT(v.id) AS contrataciones,
                   COALESCE(SUM(v.precio), 0) AS total
            FROM empresa_cliente e
            JOIN venta v ON v.empresa_id = e.id
            GROUP BY e.id, e.nombre
            ORDER BY contrataciones DESC, e.nombre
            LIMIT 5
            """
        )
        clientes_top = dictfetchall(cursor)

        cursor.execute(
            """
            SELECT cat.id, cat.nombre, COUNT(c.codigo_empleado) AS cantidad
            FROM categoria_profesional cat
            LEFT JOIN consultor c ON c.categoria_id = cat.id
            GROUP BY cat.id, cat.nombre
            ORDER BY cat.id
            """
        )
        por_categoria = dictfetchall(cursor)

    for c in por_categoria:
        c['porcentaje'] = round(100 * c['cantidad'] / total_consultores) if total_consultores else 0

    estados = {'En curso': 0, 'Próximo': 0, 'Finalizado': 0}
    for v in ventas:
        estados[v['estado']] += 1

    datos = {
        'total_consultores': total_consultores,
        'total_empresas': total_empresas,
        'total_proyectos': total_proyectos,
        'total_ventas': len(ventas),
        'en_curso': estados['En curso'],
        'proximas': estados['Próximo'],
        'finalizadas': estados['Finalizado'],
        'ventas_recientes': ventas[:8],
        'proyectos_top': proyectos_top,
        'clientes_top': clientes_top,
        'por_categoria': por_categoria,
    }

    # Los números de dinero solo se calculan y envían si el rol puede verlos.
    if tiene_permiso(request, 'finanzas.ver'):
        ingresos = sum((v['precio'] or 0) for v in ventas)
        costes = sum((v['coste'] or 0) for v in ventas)
        datos.update(ingresos=ingresos, costes=costes, margen=ingresos - costes)

    return renderizar(request, 'myapp/inicio.html', datos)


# ---------- CONSULTORES (administrador y RRHH modifican) ----------

@login_requerido
@permiso_requerido('consultores', solo_post=True)
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

    return renderizar(request, 'myapp/consultores.html', {
        'consultores': lista_consultores,
        'categorias': categorias,
        'posibles_jefes': posibles_jefes,
    })


@login_requerido
@permiso_requerido('consultores')
def eliminar_consultor(request, pk):
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM consultor WHERE codigo_empleado = %s", [pk])
        messages.success(request, 'Consultor eliminado.')
    except IntegrityError:
        messages.error(
            request,
            'No se puede eliminar: el consultor tiene ventas a cargo, personas que dependen de él o movimientos en la caja.',
        )
    return redirect('consultores')


# ---------- EMPRESAS (solo administrador modifica) ----------

@login_requerido
@permiso_requerido('empresas', solo_post=True)
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
        cursor.execute(
            """
            SELECT e.id, e.nombre, e.direccion, e.cif,
                   COUNT(v.id) AS proyectos_contratados
            FROM empresa_cliente e
            LEFT JOIN venta v ON v.empresa_id = e.id
            GROUP BY e.id, e.nombre, e.direccion, e.cif
            ORDER BY e.nombre
            """
        )
        lista_empresas = dictfetchall(cursor)

        cursor.execute("SELECT numero, empresa_id FROM telefono")
        telefonos = dictfetchall(cursor)

    telefonos_por_empresa = {}
    for t in telefonos:
        telefonos_por_empresa.setdefault(t['empresa_id'], []).append(t['numero'])

    for e in lista_empresas:
        e['telefonos'] = telefonos_por_empresa.get(e['id'], [])

    return renderizar(request, 'myapp/empresas.html', {'empresas': lista_empresas})


@login_requerido
@permiso_requerido('empresas')
def eliminar_empresa(request, pk):
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM telefono WHERE empresa_id = %s", [pk])
                cursor.execute("DELETE FROM empresa_cliente WHERE id = %s", [pk])
        messages.success(request, 'Empresa eliminada.')
    except IntegrityError:
        messages.error(request, 'No se puede eliminar: la empresa tiene proyectos contratados o movimientos en la caja.')
    return redirect('empresas')


# ---------- PROYECTOS (solo administrador modifica) ----------

@login_requerido
@permiso_requerido('proyectos', solo_post=True)
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
        cursor.execute(
            """
            SELECT p.id, p.descripcion, p.coste,
                   COUNT(v.id) AS veces_vendido,
                   GROUP_CONCAT(DISTINCT e.nombre ORDER BY e.nombre SEPARATOR ', ') AS clientes
            FROM proyecto p
            LEFT JOIN venta v ON v.proyecto_id = p.id
            LEFT JOIN empresa_cliente e ON v.empresa_id = e.id
            GROUP BY p.id, p.descripcion, p.coste
            ORDER BY p.id DESC
            """
        )
        lista_proyectos = dictfetchall(cursor)

    return renderizar(request, 'myapp/proyectos.html', {'proyectos': lista_proyectos})


@login_requerido
@permiso_requerido('proyectos')
def eliminar_proyecto(request, pk):
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM proyecto WHERE id = %s", [pk])
        messages.success(request, 'Proyecto eliminado.')
    except IntegrityError:
        messages.error(request, 'No se puede eliminar: el proyecto ya fue vendido a alguna empresa.')
    return redirect('proyectos')


# ---------- DETALLES (se abren al hacer clic en cada elemento) ----------

def _primero_o_404(filas, mensaje):
    if not filas:
        raise Http404(mensaje)
    return filas[0]


@login_requerido
def consultor_detalle(request, pk):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.codigo_empleado, c.nombre, c.sueldo,
                   cat.nombre AS categoria_nombre, cat.salario_recomendado,
                   jefe.codigo_empleado AS jefe_id, jefe.nombre AS jefe_nombre
            FROM consultor c
            JOIN categoria_profesional cat ON c.categoria_id = cat.id
            LEFT JOIN consultor jefe ON c.jefe_id = jefe.codigo_empleado
            WHERE c.codigo_empleado = %s
            """,
            [pk],
        )
        consultor = _primero_o_404(dictfetchall(cursor), 'Consultor no encontrado')

        cursor.execute(
            "SELECT codigo_empleado, nombre FROM consultor WHERE jefe_id = %s ORDER BY nombre",
            [pk],
        )
        subordinados = dictfetchall(cursor)

        ventas = _ventas(cursor, 'WHERE v.consultor_id = %s', [pk])

    diferencia = None
    if consultor['sueldo'] is not None and consultor['salario_recomendado'] is not None:
        diferencia = consultor['sueldo'] - consultor['salario_recomendado']

    return renderizar(request, 'myapp/consultor_detalle.html', {
        'consultor': consultor,
        'subordinados': subordinados,
        'ventas': ventas,
        'diferencia': diferencia,
        'diferencia_abs': abs(diferencia) if diferencia is not None else None,
    })


@login_requerido
def empresa_detalle(request, pk):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, nombre, direccion, cif FROM empresa_cliente WHERE id = %s", [pk]
        )
        empresa = _primero_o_404(dictfetchall(cursor), 'Empresa no encontrada')

        cursor.execute("SELECT numero FROM telefono WHERE empresa_id = %s ORDER BY id", [pk])
        telefonos = [fila[0] for fila in cursor.fetchall()]

        ventas = _ventas(cursor, 'WHERE v.empresa_id = %s', [pk])

    datos = {'empresa': empresa, 'telefonos': telefonos, 'ventas': ventas}
    if tiene_permiso(request, 'finanzas.ver'):
        datos['total_contratado'] = sum((v['precio'] or 0) for v in ventas)
    return renderizar(request, 'myapp/empresa_detalle.html', datos)


@login_requerido
def proyecto_detalle(request, pk):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, descripcion, coste FROM proyecto WHERE id = %s", [pk])
        proyecto = _primero_o_404(dictfetchall(cursor), 'Proyecto no encontrado')

        ventas = _ventas(cursor, 'WHERE v.proyecto_id = %s', [pk])

    datos = {'proyecto': proyecto, 'ventas': ventas, 'veces_vendido': len(ventas)}
    if tiene_permiso(request, 'finanzas.ver'):
        ingresos = sum((v['precio'] or 0) for v in ventas)
        costes = (proyecto['coste'] or 0) * len(ventas)
        datos.update(ingresos=ingresos, costes=costes, margen=ingresos - costes)
    return renderizar(request, 'myapp/proyecto_detalle.html', datos)


# ---------- EDICIÓN (se abre con el botón "Editar" de cada detalle) ----------

LIMITE_DINERO = Decimal('99999999.99')   # lo que entra en un DECIMAL(10,2)


def _entero(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _decimal(valor, maximo=LIMITE_DINERO):
    """Devuelve un Decimal entre 0 y LIMITE_DINERO con 2 decimales, o None si no sirve."""
    try:
        numero = Decimal(str(valor).strip().replace(',', '.'))
    except (InvalidOperation, ValueError):
        return None
    if not numero.is_finite() or numero < 0 or numero > maximo:
        return None
    return numero.quantize(Decimal('0.01'))


def _descendientes(todos, raiz):
    """Ids de todas las personas que dependen (directa o indirectamente) de `raiz`."""
    hijos = {}
    for c in todos:
        hijos.setdefault(c['jefe_id'], []).append(c['codigo_empleado'])
    resultado, pendientes = set(), [raiz]
    while pendientes:
        actual = pendientes.pop()
        for h in hijos.get(actual, []):
            if h not in resultado:
                resultado.add(h)
                pendientes.append(h)
    return resultado


@login_requerido
@permiso_requerido('consultores')
def consultor_editar(request, pk):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT codigo_empleado, nombre, sueldo, categoria_id, jefe_id "
            "FROM consultor WHERE codigo_empleado = %s",
            [pk],
        )
        consultor = _primero_o_404(dictfetchall(cursor), 'Consultor no encontrado')

        cursor.execute("SELECT id, nombre FROM categoria_profesional ORDER BY id")
        categorias = dictfetchall(cursor)

        cursor.execute("SELECT codigo_empleado, nombre, jefe_id FROM consultor ORDER BY nombre")
        todos = dictfetchall(cursor)

    # Puede depender de cualquiera, menos de sí mismo ni de quienes dependen de él
    # (si no, se armaría un círculo: A es jefe de B y B es jefe de A).
    excluidos = _descendientes(todos, pk) | {pk}
    posibles_jefes = [c for c in todos if c['codigo_empleado'] not in excluidos]

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        sueldo_texto = request.POST.get('sueldo', '')
        sueldo = _decimal(sueldo_texto)
        categoria_id = _entero(request.POST.get('categoria'))
        jefe_id = _entero(request.POST.get('jefe'))

        errores = []
        if not nombre:
            errores.append('El nombre es obligatorio.')
        elif len(nombre) > 100:
            errores.append('El nombre no puede superar los 100 caracteres.')
        if sueldo is None:
            errores.append('El sueldo tiene que ser un número entre 0 y 99.999.999,99.')
        if categoria_id not in {c['id'] for c in categorias}:
            errores.append('Elegí una categoría válida.')
        if jefe_id is not None and jefe_id not in {c['codigo_empleado'] for c in posibles_jefes}:
            errores.append('El jefe elegido no es válido.')

        if not errores:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE consultor SET nombre = %s, sueldo = %s, categoria_id = %s, jefe_id = %s "
                    "WHERE codigo_empleado = %s",
                    [nombre, sueldo, categoria_id, jefe_id, pk],
                )
            messages.success(request, 'Consultor actualizado correctamente.')
            return redirect('consultor_detalle', pk=pk)

        for e in errores:
            messages.error(request, e)
        # Se vuelve a mostrar el formulario con lo que la persona había escrito.
        consultor.update(nombre=nombre, sueldo=sueldo_texto,
                         categoria_id=categoria_id, jefe_id=jefe_id)

    return renderizar(request, 'myapp/consultor_editar.html', {
        'consultor': consultor,
        'categorias': categorias,
        'posibles_jefes': posibles_jefes,
    })


@login_requerido
@permiso_requerido('empresas')
def empresa_editar(request, pk):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, nombre, direccion, cif FROM empresa_cliente WHERE id = %s", [pk]
        )
        empresa = _primero_o_404(dictfetchall(cursor), 'Empresa no encontrada')

        cursor.execute("SELECT numero FROM telefono WHERE empresa_id = %s ORDER BY id", [pk])
        telefonos_texto = '\n'.join(fila[0] for fila in cursor.fetchall())

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        direccion = request.POST.get('direccion', '').strip()
        cif = request.POST.get('cif', '').strip()
        telefonos_texto = request.POST.get('telefonos', '')
        # Un teléfono por línea, sin vacíos ni repetidos.
        telefonos = list(dict.fromkeys(
            linea.strip() for linea in telefonos_texto.splitlines() if linea.strip()
        ))

        errores = []
        if not nombre:
            errores.append('El nombre es obligatorio.')
        elif len(nombre) > 100:
            errores.append('El nombre no puede superar los 100 caracteres.')
        if len(direccion) > 200:
            errores.append('La dirección no puede superar los 200 caracteres.')
        if not cif:
            errores.append('El CIF es obligatorio.')
        elif len(cif) > 15:
            errores.append('El CIF no puede superar los 15 caracteres.')
        if any(len(t) > 20 for t in telefonos):
            errores.append('Cada teléfono puede tener hasta 20 caracteres.')

        if not errores:
            try:
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "UPDATE empresa_cliente SET nombre = %s, direccion = %s, cif = %s "
                            "WHERE id = %s",
                            [nombre, direccion or None, cif, pk],
                        )
                        cursor.execute("DELETE FROM telefono WHERE empresa_id = %s", [pk])
                        for numero in telefonos:
                            cursor.execute(
                                "INSERT INTO telefono (numero, empresa_id) VALUES (%s, %s)",
                                [numero, pk],
                            )
                messages.success(request, 'Empresa actualizada correctamente.')
                return redirect('empresa_detalle', pk=pk)
            except IntegrityError:
                errores.append('Ya existe otra empresa con ese CIF.')

        for e in errores:
            messages.error(request, e)
        empresa.update(nombre=nombre, direccion=direccion, cif=cif)

    return renderizar(request, 'myapp/empresa_editar.html', {
        'empresa': empresa,
        'telefonos_texto': telefonos_texto,
    })


@login_requerido
@permiso_requerido('proyectos')
def proyecto_editar(request, pk):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, descripcion, coste FROM proyecto WHERE id = %s", [pk])
        proyecto = _primero_o_404(dictfetchall(cursor), 'Proyecto no encontrado')

    if request.method == 'POST':
        descripcion = request.POST.get('descripcion', '').strip()
        coste_texto = request.POST.get('coste', '')
        coste = _decimal(coste_texto)

        errores = []
        if not descripcion:
            errores.append('La descripción es obligatoria.')
        if coste is None:
            errores.append('El coste tiene que ser un número entre 0 y 99.999.999,99.')

        if not errores:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE proyecto SET descripcion = %s, coste = %s WHERE id = %s",
                    [descripcion, coste, pk],
                )
            messages.success(request, 'Proyecto actualizado correctamente.')
            return redirect('proyecto_detalle', pk=pk)

        for e in errores:
            messages.error(request, e)
        proyecto.update(descripcion=descripcion, coste=coste_texto)

    return renderizar(request, 'myapp/proyecto_editar.html', {'proyecto': proyecto})


# ---------- CAJA (permisos caja.ver y caja.modificar) ----------

# Cada categoría pertenece a un tipo. El tipo NO lo elige la persona: sale de acá.
CATEGORIAS_CAJA = {
    'cobro_proyecto': {'nombre': 'Cobro de proyecto', 'tipo': 'ingreso'},
    'cuota':          {'nombre': 'Cobro de cuota',    'tipo': 'ingreso'},
    'otro_ingreso':   {'nombre': 'Otro ingreso',      'tipo': 'ingreso'},
    'aporte':         {'nombre': 'Aporte de capital', 'tipo': 'ingreso'},
    'sueldo':         {'nombre': 'Pago de sueldo',    'tipo': 'egreso'},
    'gasto':          {'nombre': 'Gasto operativo',   'tipo': 'egreso'},
    'impuesto':       {'nombre': 'Impuestos',         'tipo': 'egreso'},
    'inversion':      {'nombre': 'Inversión',         'tipo': 'egreso'},
    'otro_egreso':    {'nombre': 'Otro egreso',       'tipo': 'egreso'},
}
TIPOS_CAJA = ('ingreso', 'egreso')
LIMITE_CAJA = Decimal('999999999999.99')   # lo que entra en DECIMAL(14,2)
MAX_MOVIMIENTOS_EN_PANTALLA = 300


def _fecha(texto):
    try:
        return datetime.strptime(texto, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _filtros_caja(request):
    """Arma el WHERE con los filtros de la URL (?desde=...&empresa=...). Valores siempre parametrizados."""
    condiciones, parametros, activos = [], [], {}

    desde = _fecha(request.GET.get('desde'))
    if desde:
        condiciones.append('m.fecha >= %s')
        parametros.append(desde)
        activos['desde'] = desde.isoformat()

    hasta = _fecha(request.GET.get('hasta'))
    if hasta:
        condiciones.append('m.fecha <= %s')
        parametros.append(hasta)
        activos['hasta'] = hasta.isoformat()

    empresa = _entero(request.GET.get('empresa'))
    if empresa is not None:
        condiciones.append('m.empresa_id = %s')
        parametros.append(empresa)
        activos['empresa'] = empresa

    consultor = _entero(request.GET.get('consultor'))
    if consultor is not None:
        condiciones.append('m.consultor_id = %s')
        parametros.append(consultor)
        activos['consultor'] = consultor

    categoria = request.GET.get('categoria')
    if categoria in CATEGORIAS_CAJA:
        condiciones.append('m.categoria = %s')
        parametros.append(categoria)
        activos['categoria'] = categoria

    tipo = request.GET.get('tipo')
    if tipo in TIPOS_CAJA:
        condiciones.append('m.tipo = %s')
        parametros.append(tipo)
        activos['tipo'] = tipo

    where = ('WHERE ' + ' AND '.join(condiciones)) if condiciones else ''
    return where, parametros, activos


def _lista_categorias(tipo=None):
    return [
        {'clave': clave, 'nombre': datos['nombre']}
        for clave, datos in CATEGORIAS_CAJA.items()
        if tipo is None or datos['tipo'] == tipo
    ]


@login_requerido
@requiere('caja.ver')
def caja(request):
    where, parametros, activos = _filtros_caja(request)

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT COUNT(*) AS cantidad,
                       COALESCE(SUM(CASE WHEN m.tipo = 'ingreso' THEN m.monto END), 0) AS ingresos,
                       COALESCE(SUM(CASE WHEN m.tipo = 'egreso' THEN m.monto END), 0) AS egresos,
                       COALESCE(SUM(CASE WHEN m.categoria = 'aporte' THEN m.monto END), 0) AS aportes,
                       COALESCE(SUM(CASE WHEN m.categoria = 'inversion' THEN m.monto END), 0) AS inversiones,
                       COALESCE(SUM(CASE WHEN m.categoria = 'cuota' THEN m.monto END), 0) AS cuotas
                FROM movimiento_caja m
                {where}
                """,
                parametros,
            )
            t = dictfetchall(cursor)[0]

            cursor.execute(
                f"""
                SELECT m.id, m.fecha, m.tipo, m.categoria, m.monto, m.descripcion,
                       m.cuota_numero, m.cuotas_total, m.registrado_por,
                       e.id AS empresa_id, e.nombre AS empresa,
                       c.codigo_empleado AS consultor_id, c.nombre AS consultor,
                       p.id AS proyecto_id, p.descripcion AS proyecto
                FROM movimiento_caja m
                LEFT JOIN empresa_cliente e ON m.empresa_id = e.id
                LEFT JOIN consultor c ON m.consultor_id = c.codigo_empleado
                LEFT JOIN venta v ON m.venta_id = v.id
                LEFT JOIN proyecto p ON v.proyecto_id = p.id
                {where}
                ORDER BY m.fecha DESC, m.id DESC
                LIMIT {MAX_MOVIMIENTOS_EN_PANTALLA}
                """,
                parametros,
            )
            movimientos = dictfetchall(cursor)

            cursor.execute("SELECT id, nombre FROM empresa_cliente ORDER BY nombre")
            empresas_lista = dictfetchall(cursor)
            cursor.execute(
                "SELECT codigo_empleado, nombre, sueldo FROM consultor ORDER BY nombre"
            )
            consultores_lista = dictfetchall(cursor)

            # Acumulado por empresa: lo facturado (contrataciones) contra lo realmente cobrado.
            cursor.execute(
                "SELECT empresa_id, COALESCE(SUM(precio), 0) AS facturado "
                "FROM venta GROUP BY empresa_id"
            )
            facturado = {f['empresa_id']: f['facturado'] for f in dictfetchall(cursor)}
            cursor.execute(
                """
                SELECT empresa_id,
                       COALESCE(SUM(CASE WHEN categoria IN ('cobro_proyecto', 'cuota')
                                         THEN monto ELSE 0 END), 0) AS cobrado,
                       COALESCE(SUM(CASE WHEN tipo = 'egreso' THEN monto ELSE 0 END), 0) AS gastos
                FROM movimiento_caja
                WHERE empresa_id IS NOT NULL
                GROUP BY empresa_id
                """
            )
            caja_por_empresa = {f['empresa_id']: f for f in dictfetchall(cursor)}

            # Acumulado por consultor: sueldos pagados y ventas a su cargo.
            cursor.execute(
                "SELECT consultor_id, COUNT(*) AS ventas, COALESCE(SUM(precio), 0) AS facturado "
                "FROM venta GROUP BY consultor_id"
            )
            ventas_por_consultor = {f['consultor_id']: f for f in dictfetchall(cursor)}
            cursor.execute(
                "SELECT consultor_id, COALESCE(SUM(monto), 0) AS pagado "
                "FROM movimiento_caja WHERE categoria = 'sueldo' AND consultor_id IS NOT NULL "
                "GROUP BY consultor_id"
            )
            sueldos_pagados = {f['consultor_id']: f['pagado'] for f in dictfetchall(cursor)}
    except ProgrammingError as error:
        if error.args and error.args[0] == 1146:       # "la tabla no existe"
            return renderizar(request, 'myapp/caja.html', {'falta_tabla': True})
        raise

    ingresos, egresos = t['ingresos'], t['egresos']
    aportes, inversiones = t['aportes'], t['inversiones']
    gastos = egresos - inversiones
    resumen = {
        'saldo': ingresos - egresos,
        'ingresos': ingresos,
        'gastos': gastos,
        'inversiones': inversiones,
        'ganancia': (ingresos - aportes) - gastos,
        'cuotas': t['cuotas'],
        'cantidad': t['cantidad'],
    }

    for m in movimientos:
        m['categoria_nombre'] = CATEGORIAS_CAJA.get(m['categoria'], {}).get('nombre', m['categoria'])

    resumen_empresas = []
    for e in empresas_lista:
        datos = caja_por_empresa.get(e['id'], {})
        fact = facturado.get(e['id'], Decimal('0'))
        cobrado = datos.get('cobrado', Decimal('0'))
        gastos_e = datos.get('gastos', Decimal('0'))
        resumen_empresas.append({
            'id': e['id'], 'nombre': e['nombre'],
            'facturado': fact, 'cobrado': cobrado,
            'pendiente': fact - cobrado,
            'gastos': gastos_e,
            'resultado': cobrado - gastos_e,
        })

    resumen_consultores = []
    for c in consultores_lista:
        ventas = ventas_por_consultor.get(c['codigo_empleado'], {})
        resumen_consultores.append({
            'codigo_empleado': c['codigo_empleado'], 'nombre': c['nombre'],
            'sueldo': c['sueldo'],
            'pagado': sueldos_pagados.get(c['codigo_empleado'], Decimal('0')),
            'ventas': ventas.get('ventas', 0),
            'facturado': ventas.get('facturado', Decimal('0')),
        })

    return renderizar(request, 'myapp/caja.html', {
        'resumen': resumen,
        'movimientos': movimientos,
        'hay_mas': t['cantidad'] > MAX_MOVIMIENTOS_EN_PANTALLA,
        'limite': MAX_MOVIMIENTOS_EN_PANTALLA,
        'filtros': activos,
        'empresas_filtro': empresas_lista,
        'consultores_filtro': consultores_lista,
        'categorias_filtro': _lista_categorias(),
        'resumen_empresas': resumen_empresas,
        'resumen_consultores': resumen_consultores,
    })


def _opciones_caja(cursor):
    """Empresas, consultores y contrataciones para los selects del formulario."""
    cursor.execute("SELECT id, nombre FROM empresa_cliente ORDER BY nombre")
    empresas_lista = dictfetchall(cursor)
    cursor.execute("SELECT codigo_empleado, nombre FROM consultor ORDER BY nombre")
    consultores_lista = dictfetchall(cursor)
    return empresas_lista, consultores_lista, _ventas(cursor)


def _leer_movimiento(post, empresas_lista, consultores_lista, ventas_lista):
    """Valida el formulario de un movimiento. Devuelve (datos, errores)."""
    errores = []
    fecha = _fecha(post.get('fecha'))
    categoria = post.get('categoria')
    monto_texto = post.get('monto', '')
    monto = _decimal(monto_texto, LIMITE_CAJA)
    descripcion = post.get('descripcion', '').strip()
    empresa_id = _entero(post.get('empresa'))
    venta_id = _entero(post.get('venta'))
    consultor_id = _entero(post.get('consultor'))
    cuota_numero = _entero(post.get('cuota_numero'))
    cuotas_total = _entero(post.get('cuotas_total'))

    if fecha is None:
        errores.append('Ingresá una fecha válida.')
    if categoria not in CATEGORIAS_CAJA:
        errores.append('Elegí una categoría.')
    if monto is None or monto <= 0:
        errores.append('El monto tiene que ser un número mayor a 0 (máximo 999.999.999.999,99).')
    if len(descripcion) > 200:
        errores.append('La descripción no puede superar los 200 caracteres.')

    ventas_por_id = {v['id']: v for v in ventas_lista}
    if venta_id is not None:
        if venta_id in ventas_por_id:
            empresa_id = ventas_por_id[venta_id]['empresa_id']   # la empresa sale de la contratación
        else:
            errores.append('La contratación elegida no es válida.')
    if empresa_id is not None and empresa_id not in {e['id'] for e in empresas_lista}:
        errores.append('La empresa elegida no es válida.')
    if consultor_id is not None and consultor_id not in {c['codigo_empleado'] for c in consultores_lista}:
        errores.append('El consultor elegido no es válido.')

    if categoria in ('cobro_proyecto', 'cuota') and empresa_id is None:
        errores.append('Un cobro tiene que estar asociado a una empresa (o a una contratación).')
    if categoria == 'sueldo' and consultor_id is None:
        errores.append('Elegí a qué consultor corresponde el sueldo.')

    if categoria == 'cuota' and (cuota_numero or cuotas_total):
        if not (cuota_numero and cuotas_total and 1 <= cuota_numero <= cuotas_total <= 360):
            errores.append('Cuota inválida: completá el número y el total (el número no puede superar al total).')
    if categoria != 'cuota':
        cuota_numero = cuotas_total = None

    datos = {
        'fecha': fecha.isoformat() if fecha else post.get('fecha', ''),
        'categoria': categoria or '',
        'monto_texto': monto_texto,
        'descripcion': descripcion,
        'empresa_id': empresa_id,
        'venta_id': venta_id,
        'consultor_id': consultor_id,
        'cuota_numero': cuota_numero,
        'cuotas_total': cuotas_total,
        # valores ya listos para la base
        'fecha_db': fecha,
        'monto_db': monto,
        'tipo_db': CATEGORIAS_CAJA[categoria]['tipo'] if categoria in CATEGORIAS_CAJA else None,
    }
    return datos, errores


def _contexto_form_caja(mov, titulo, empresas_lista, consultores_lista, ventas_lista):
    return {
        'mov': mov,
        'titulo': titulo,
        'empresas_op': empresas_lista,
        'consultores_op': consultores_lista,
        'ventas_op': ventas_lista,
        'categorias_ingreso': _lista_categorias('ingreso'),
        'categorias_egreso': _lista_categorias('egreso'),
    }


@login_requerido
@requiere('caja.modificar', 'caja')
def caja_nuevo(request):
    with connection.cursor() as cursor:
        empresas_lista, consultores_lista, ventas_lista = _opciones_caja(cursor)

    if request.method == 'POST':
        mov, errores = _leer_movimiento(request.POST, empresas_lista, consultores_lista, ventas_lista)
        if not errores:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO movimiento_caja
                        (fecha, tipo, categoria, monto, descripcion, empresa_id, venta_id,
                         consultor_id, cuota_numero, cuotas_total, registrado_por)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [mov['fecha_db'], mov['tipo_db'], mov['categoria'], mov['monto_db'],
                     mov['descripcion'] or None, mov['empresa_id'], mov['venta_id'],
                     mov['consultor_id'], mov['cuota_numero'], mov['cuotas_total'],
                     usuario_actual(request)['usuario']],
                )
            messages.success(request, 'Movimiento registrado en la caja.')
            return redirect('caja')
        for e in errores:
            messages.error(request, e)
    else:
        mov = {
            'fecha': date.today().isoformat(), 'categoria': '', 'monto_texto': '',
            'descripcion': '', 'venta_id': None, 'cuota_numero': None, 'cuotas_total': None,
            'empresa_id': _entero(request.GET.get('empresa')),
            'consultor_id': _entero(request.GET.get('consultor')),
        }

    return renderizar(request, 'myapp/caja_form.html', _contexto_form_caja(
        mov, 'Nuevo movimiento', empresas_lista, consultores_lista, ventas_lista))


@login_requerido
@requiere('caja.modificar', 'caja')
def caja_editar(request, pk):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, fecha, categoria, monto, descripcion, empresa_id, venta_id, "
            "consultor_id, cuota_numero, cuotas_total FROM movimiento_caja WHERE id = %s",
            [pk],
        )
        fila = _primero_o_404(dictfetchall(cursor), 'Movimiento no encontrado')
        empresas_lista, consultores_lista, ventas_lista = _opciones_caja(cursor)

    if request.method == 'POST':
        mov, errores = _leer_movimiento(request.POST, empresas_lista, consultores_lista, ventas_lista)
        if not errores:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE movimiento_caja
                    SET fecha = %s, tipo = %s, categoria = %s, monto = %s, descripcion = %s,
                        empresa_id = %s, venta_id = %s, consultor_id = %s,
                        cuota_numero = %s, cuotas_total = %s
                    WHERE id = %s
                    """,
                    [mov['fecha_db'], mov['tipo_db'], mov['categoria'], mov['monto_db'],
                     mov['descripcion'] or None, mov['empresa_id'], mov['venta_id'],
                     mov['consultor_id'], mov['cuota_numero'], mov['cuotas_total'], pk],
                )
            messages.success(request, 'Movimiento actualizado correctamente.')
            return redirect('caja')
        for e in errores:
            messages.error(request, e)
    else:
        mov = {
            'fecha': fila['fecha'].isoformat(), 'categoria': fila['categoria'],
            'monto_texto': str(fila['monto']), 'descripcion': fila['descripcion'] or '',
            'empresa_id': fila['empresa_id'], 'venta_id': fila['venta_id'],
            'consultor_id': fila['consultor_id'],
            'cuota_numero': fila['cuota_numero'], 'cuotas_total': fila['cuotas_total'],
        }

    contexto = _contexto_form_caja(
        mov, f'Editar movimiento #{pk}', empresas_lista, consultores_lista, ventas_lista)
    contexto['editando'] = True
    return renderizar(request, 'myapp/caja_form.html', contexto)


@login_requerido
@requiere('caja.modificar', 'caja')
def caja_eliminar(request, pk):
    if request.method != 'POST':
        return redirect('caja')
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM movimiento_caja WHERE id = %s", [pk])
    messages.success(request, 'Movimiento eliminado.')
    return redirect('caja')


# ---------- PANEL DE USUARIOS (solo la cuenta principal) ----------

def _datos_permisos(rol, extras):
    """Permisos listos para dibujar en el formulario: cuáles trae el rol y cuáles son extra."""
    del_rol = permisos_efectivos(rol, set()) if rol in ROLES else set()
    return [
        {'clave': clave, 'etiqueta': datos['etiqueta'], 'descripcion': datos['descripcion'],
         'del_rol': clave in del_rol, 'marcado': clave in extras and clave not in del_rol}
        for clave, datos in PERMISOS.items()
    ]


@login_requerido
@requiere('usuarios.gestionar')
def usuarios(request):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, usuario, rol, es_principal, activo, creado_en "
            "FROM usuarios ORDER BY es_principal DESC, usuario"
        )
        lista = dictfetchall(cursor)
        cursor.execute("SELECT usuario_id, permiso FROM usuario_permiso")
        extras_por_usuario = {}
        for usuario_id, permiso in cursor.fetchall():
            extras_por_usuario.setdefault(usuario_id, set()).add(permiso)

    for u in lista:
        extras = extras_por_usuario.get(u['id'], set())
        efectivos = set(PERMISOS) if u['es_principal'] else permisos_efectivos(u['rol'], extras)
        u['rol_nombre'] = 'Administrador principal' if u['es_principal'] else ROLES.get(u['rol'], u['rol'])
        u['permisos'] = [PERMISOS[clave]['etiqueta'] for clave in PERMISOS if clave in efectivos]
        u['cantidad_extras'] = len(extras)

    return renderizar(request, 'myapp/usuarios.html', {
        'lista_usuarios': lista,
        'pendientes': sum(1 for u in lista if not u['activo']),
    })


@login_requerido
@requiere('usuarios.gestionar')
def usuario_editar(request, pk):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, usuario, rol, es_principal, activo, creado_en FROM usuarios WHERE id = %s",
            [pk],
        )
        objetivo = _primero_o_404(dictfetchall(cursor), 'Usuario no encontrado')
        cursor.execute("SELECT permiso FROM usuario_permiso WHERE usuario_id = %s", [pk])
        extras = {fila[0] for fila in cursor.fetchall()}

    principal = bool(objetivo['es_principal'])

    if request.method == 'POST':
        errores = []
        if principal:
            # La cuenta principal no se puede degradar, desactivar ni limitar.
            rol, activo, marcados = 'administrador', 1, set()
        else:
            rol = request.POST.get('rol')
            if rol not in ROLES:
                errores.append('Elegí un rol válido.')
            activo = 1 if request.POST.get('activo') else 0
            marcados = set(request.POST.getlist('permisos')) & set(PERMISOS)
        extras_nuevos = marcados - (permisos_efectivos(rol, set()) if rol in ROLES else set())

        nueva_clave = request.POST.get('contrasena', '')
        if nueva_clave:
            errores += validar_clave(nueva_clave, objetivo['usuario'])

        if not errores:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE usuarios SET rol = %s, activo = %s WHERE id = %s", [rol, activo, pk]
                    )
                    cursor.execute("DELETE FROM usuario_permiso WHERE usuario_id = %s", [pk])
                    for permiso in sorted(extras_nuevos):
                        cursor.execute(
                            "INSERT INTO usuario_permiso (usuario_id, permiso) VALUES (%s, %s)",
                            [pk, permiso],
                        )
                    if nueva_clave:
                        cursor.execute(
                            "UPDATE usuarios SET contrasena = %s WHERE id = %s",
                            [make_password(nueva_clave), pk],
                        )
            messages.success(request, f'Usuario «{objetivo["usuario"]}» actualizado.')
            return redirect('usuarios')

        for e in errores:
            messages.error(request, e)
        if not principal:
            if rol in ROLES:
                objetivo['rol'] = rol
            objetivo['activo'] = activo
            extras = marcados

    return renderizar(request, 'myapp/usuario_editar.html', {
        'objetivo': objetivo,
        'principal': principal,
        'roles': [{'clave': clave, 'nombre': nombre} for clave, nombre in ROLES.items()],
        'permisos_lista': _datos_permisos(objetivo['rol'], extras),
        'presets': {rol: sorted(permisos_efectivos(rol, set())) for rol in ROLES},
    })


@login_requerido
@requiere('usuarios.gestionar')
def usuario_eliminar(request, pk):
    if request.method != 'POST':
        return redirect('usuarios')
    with connection.cursor() as cursor:
        cursor.execute("SELECT usuario, es_principal FROM usuarios WHERE id = %s", [pk])
        fila = cursor.fetchone()
        if not fila:
            raise Http404('Usuario no encontrado')
        if fila[1]:
            messages.error(request, 'La cuenta principal no se puede eliminar.')
            return redirect('usuarios')
        cursor.execute("DELETE FROM usuarios WHERE id = %s", [pk])   # sus permisos se borran solos
    messages.success(request, f'Usuario «{fila[0]}» eliminado.')
    return redirect('usuarios')