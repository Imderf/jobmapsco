<?php
// Copiar como config.php (no se sube a git) con los datos de la base del servidor.
return [
    'dsn' => 'mysql:host=localhost;dbname=mapa_empleo;charset=utf8mb4',
    'usuario' => 'mapa_empleo',
    'clave' => '',
    'sal' => '',   // texto aleatorio largo: cifra las IP para limitar intentos
];
