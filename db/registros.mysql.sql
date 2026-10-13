-- Registros del Mapa del Empleo (MySQL 8 / MariaDB 10.5+). Correr una vez en la base del servidor.
CREATE TABLE IF NOT EXISTS registros (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(80) NOT NULL,
  correo VARCHAR(120) NOT NULL,
  acepto TINYINT(1) NOT NULL,          -- consentimiento (Ley 1581 de 2012): siempre 1
  politica VARCHAR(80) NOT NULL,       -- versión de la política que aceptó
  ip_hash CHAR(64) NOT NULL,           -- IP cifrada (SHA-256 con sal): solo para limitar intentos
  creado DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY correo_unico (correo),
  KEY ip_reciente (ip_hash, creado)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
