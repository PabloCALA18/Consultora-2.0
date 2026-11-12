USE empresa_consultora;

-- Roles disponibles
CREATE TABLE IF NOT EXISTS rol (
    codigo VARCHAR(20) PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL
) ENGINE=InnoDB;

INSERT IGNORE INTO rol (codigo, nombre) VALUES
    ('administrador', 'Administrador'),
    ('rrhh', 'Recursos Humanos'),
    ('operario', 'Operario');

-- Cuentas utilizadas por el login de la aplicación.
CREATE TABLE IF NOT EXISTS usuarios (
    id INT NOT NULL AUTO_INCREMENT,
    usuario VARCHAR(50) NOT NULL,
    contrasena VARCHAR(255) NOT NULL,
    rol VARCHAR(20) NOT NULL DEFAULT 'operario',
    es_principal TINYINT(1) NOT NULL DEFAULT 0,
    activo TINYINT(1) NOT NULL DEFAULT 1,
    creado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    principal_unico TINYINT GENERATED ALWAYS AS (IF(es_principal = 1, 1, NULL)) VIRTUAL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_usuarios_usuario (usuario),
    UNIQUE KEY uq_usuarios_principal (principal_unico),
    CONSTRAINT fk_usuarios_rol FOREIGN KEY (rol) REFERENCES rol (codigo)
) ENGINE=InnoDB;

-- Permisos adicionales asignados a cada usuario.
CREATE TABLE IF NOT EXISTS usuario_permiso (
    usuario_id INT NOT NULL,
    permiso VARCHAR(40) NOT NULL,
    PRIMARY KEY (usuario_id, permiso),
    CONSTRAINT fk_usuario_permiso_usuario FOREIGN KEY (usuario_id)
        REFERENCES usuarios (id) ON DELETE CASCADE
) ENGINE=InnoDB;

SELECT * FROM usuarios;
