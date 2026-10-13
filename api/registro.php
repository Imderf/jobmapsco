<?php
// Recibe el registro del popup (JSON por POST) y lo guarda en MySQL. Responde JSON.
// Credenciales en config.php (no va a git; ver config.example.php).
header('Content-Type: application/json; charset=utf-8');
header('X-Content-Type-Options: nosniff');

function responder($codigo, $cuerpo) {
    http_response_code($codigo);
    echo json_encode($cuerpo);
    exit;
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') responder(405, ['ok' => false]);
$config = require __DIR__ . '/config.php';

$d = json_decode((string) file_get_contents('php://input', false, null, 0, 4096), true);
if (!is_array($d)) responder(400, ['ok' => false, 'error' => 'formato']);
if (!empty($d['web'])) responder(200, ['ok' => true]);   // campo trampa: solo lo llenan los bots

$nombre = trim((string) ($d['nombre'] ?? ''));
$correo = mb_strtolower(trim((string) ($d['correo'] ?? '')));
$politica = trim((string) ($d['politica'] ?? ''));
if ($nombre === '' || mb_strlen($nombre) > 80
    || mb_strlen($correo) > 120 || !filter_var($correo, FILTER_VALIDATE_EMAIL)
    || ($d['acepto'] ?? false) !== true
    || $politica === '' || mb_strlen($politica) > 80) {
    responder(422, ['ok' => false, 'error' => 'datos']);
}

try {
    $db = new PDO($config['dsn'], $config['usuario'], $config['clave'], [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_EMULATE_PREPARES => false,
    ]);
    $ip = hash('sha256', $config['sal'] . ($_SERVER['REMOTE_ADDR'] ?? ''));
    $q = $db->prepare('SELECT COUNT(*) FROM registros WHERE ip_hash = ? AND creado > NOW() - INTERVAL 1 HOUR');
    $q->execute([$ip]);
    if ((int) $q->fetchColumn() >= 10) responder(429, ['ok' => false, 'error' => 'intentos']);
    // el mismo correo dos veces no es error: se ignora
    $db->prepare('INSERT IGNORE INTO registros (nombre, correo, acepto, politica, ip_hash) VALUES (?, ?, 1, ?, ?)')
       ->execute([$nombre, $correo, $politica, $ip]);
    responder(200, ['ok' => true]);
} catch (Throwable $e) {
    error_log('registro: ' . $e->getMessage());
    responder(500, ['ok' => false]);
}
