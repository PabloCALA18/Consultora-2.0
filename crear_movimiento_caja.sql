USE empresa_consultora;

-- Requiere que ya existan empresa_cliente, venta y consultor.
CREATE TABLE IF NOT EXISTS movimiento_caja (
    id INT NOT NULL AUTO_INCREMENT,
    fecha DATE NOT NULL,
    tipo VARCHAR(10) NOT NULL,
    categoria VARCHAR(20) NOT NULL,
    monto DECIMAL(14,2) NOT NULL,
    descripcion VARCHAR(200) NULL,
    empresa_id INT NULL,
    venta_id INT NULL,
    consultor_id INT NULL,
    cuota_numero INT NULL,
    cuotas_total INT NULL,
    registrado_por VARCHAR(50) NOT NULL,
    creado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT chk_mov_tipo CHECK (tipo IN ('ingreso', 'egreso')),
    CONSTRAINT chk_mov_monto CHECK (monto > 0),
    CONSTRAINT fk_mov_empresa FOREIGN KEY (empresa_id) REFERENCES empresa_cliente (id),
    CONSTRAINT fk_mov_venta FOREIGN KEY (venta_id) REFERENCES venta (id),
    CONSTRAINT fk_mov_consultor FOREIGN KEY (consultor_id) REFERENCES consultor (codigo_empleado),
    INDEX idx_mov_fecha (fecha),
    INDEX idx_mov_empresa (empresa_id),
    INDEX idx_mov_consultor (consultor_id)
) ENGINE=InnoDB;

SELECT * FROM movimiento_caja;
