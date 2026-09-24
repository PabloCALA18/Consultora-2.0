<div align="center">

# 🏢 Consultora 2.0

### Sistema de gestión para consultoras — consultores, empresas clientes y proyectos, todo en un solo lugar.

![Django](https://img.shields.io/badge/Django-6.1-092E20?style=for-the-badge&logo=django&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.x-3776AB?style=for-the-badge&logo=python&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-8.0-4479A1?style=for-the-badge&logo=mysql&logoColor=white)
![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3.3-7952B3?style=for-the-badge&logo=bootstrap&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-lightgrey?style=for-the-badge)

</div>

---

## 📌 Sobre el proyecto

**Consultora 2.0** es una aplicación web hecha con **Django** que centraliza la administración de una consultora: sus **consultores**, las **empresas clientes** y los **proyectos** que se van cargando. Nace como proyecto académico, pero está pensado con una arquitectura simple y extensible para seguir creciendo.

La app usa un sistema de login propio basado en sesiones (sin depender del `User` de Django) contra una tabla `administrador` en la base de datos, y todas las consultas se manejan directamente con SQL crudo a través del cursor de Django — ideal para entender qué pasa "debajo del capó" del ORM.

---

## ✨ Funcionalidades

| Módulo | Descripción |
|---|---|
| 🔐 **Login / Logout** | Autenticación por sesión contra la tabla `administrador`, con hash de contraseñas. |
| 📊 **Panel de inicio** | Vista resumen con totales de consultores, empresas y proyectos. |
| 👨‍💼 **Consultores** | Alta, listado y eliminación. Soporta categoría profesional y jerarquía (jefe/subordinado). |
| 🏢 **Empresas clientes** | Alta, listado y eliminación, con teléfonos asociados. |
| 📁 **Proyectos** | Alta, listado y eliminación, con descripción y coste. |

---

## 🛠️ Stack tecnológico

- **Backend:** Django 6.1 + SQL crudo (`django.db.connection`)
- **Base de datos:** MySQL
- **Frontend:** Django Templates + Bootstrap 5.3.3
- **Sesiones:** Sistema de autenticación propio (sin `django.contrib.auth`)

---

## 📂 Estructura del proyecto

```
Consultora-2.0/
├── Consultora/          # Configuración del proyecto (settings, urls, wsgi/asgi)
├── myapp/               # App principal
│   ├── templates/myapp/ # Login, Inicio, Consultores, Empresas, Proyectos, Base
│   ├── views.py         # Lógica de negocio (SQL crudo)
│   ├── urls.py
│   └── models.py
├── manage.py
└── README.md
```

---

## 🚀 Puesta en marcha

```bash
# 1. Cloná el repositorio
git clone https://github.com/PabloCALA18/Consultora-2.0.git
cd Consultora-2.0

# 2. Creá y activá un entorno virtual
python -m venv venv
source venv/bin/activate      # En Windows: venv\Scripts\activate

# 3. Instalá las dependencias
pip install django mysqlclient

# 4. Configurá la base de datos en Consultora/settings.py
#    (usuario, contraseña y nombre de la base MySQL)

# 5. Corré el servidor
python manage.py runserver
```

Luego entrá a `http://127.0.0.1:8000/` 🎉

---

## 🗄️ Base de datos

La app trabaja sobre una base MySQL con (al menos) las siguientes tablas:

- `administrador`
- `consultor`
- `categoria_profesional`
- `empresa_cliente`
- `telefono`
- `proyecto`

---

## 🤝 Contribuciones

¿Tenés una idea o encontraste un bug? ¡Las contribuciones son bienvenidas!

1. Hacé un fork del proyecto
2. Creá tu rama (`git checkout -b feature/nueva-funcionalidad`)
3. Commiteá tus cambios (`git commit -m 'Agrego nueva funcionalidad'`)
4. Pusheá la rama (`git push origin feature/nueva-funcionalidad`)
5. Abrí un Pull Request

---

## 📄 Licencia

Este proyecto se distribuye bajo la licencia **MIT**. Ver el archivo `LICENSE` para más detalles.

---

<div align="center">

Hecho con 🧉 y muchas líneas de SQL crudo.

</div>
