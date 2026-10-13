<?php
// IP del visitante. Detrás de Cloudflare, REMOTE_ADDR es un nodo de Cloudflare y la IP real llega en CF-Connecting-IP.
// Ese encabezado solo se cree si la petición viene de una red de Cloudflare: si no, cualquiera lo falsificaría para saltarse el límite.
// Redes publicadas en https://www.cloudflare.com/ips/ (cambian muy rara vez)
const CLOUDFLARE = [
    '173.245.48.0/20', '103.21.244.0/22', '103.22.200.0/22', '103.31.4.0/22', '141.101.64.0/18', '108.162.192.0/18',
    '190.93.240.0/20', '188.114.96.0/20', '197.234.240.0/22', '198.41.128.0/17', '162.158.0.0/15', '104.16.0.0/13',
    '104.24.0.0/14', '172.64.0.0/13', '131.0.72.0/22',
    '2400:cb00::/32', '2606:4700::/32', '2803:f800::/32', '2405:b500::/32', '2405:8100::/32', '2a06:98c0::/29', '2c0f:f248::/32',
];

function en_red(string $ip, string $red): bool {
    [$base, $bits] = explode('/', $red);
    $a = @inet_pton($ip); $b = inet_pton($base);
    if ($a === false || strlen($a) !== strlen($b)) return false;
    $n = intdiv((int) $bits, 8); $r = (int) $bits % 8;
    return strncmp($a, $b, $n) === 0 && ($r === 0 || ((ord($a[$n]) ^ ord($b[$n])) >> (8 - $r)) === 0);
}

function ip_cliente(array $s): string {
    $ip = $s['REMOTE_ADDR'] ?? '';
    $cf = $s['HTTP_CF_CONNECTING_IP'] ?? '';
    if (!filter_var($cf, FILTER_VALIDATE_IP)) return $ip;
    foreach (CLOUDFLARE as $red) if (en_red($ip, $red)) return $cf;
    return $ip;
}

// prueba: php api/ip.php
if (PHP_SAPI === 'cli' && realpath($_SERVER['argv'][0] ?? '') === __FILE__) {
    assert(ip_cliente(['REMOTE_ADDR' => '172.71.170.146', 'HTTP_CF_CONNECTING_IP' => '199.229.67.30']) === '199.229.67.30');   // vía Cloudflare
    assert(ip_cliente(['REMOTE_ADDR' => '2606:4700:3035::1', 'HTTP_CF_CONNECTING_IP' => '2800:e2::1']) === '2800:e2::1');      // Cloudflare por IPv6
    assert(ip_cliente(['REMOTE_ADDR' => '199.229.67.30', 'HTTP_CF_CONNECTING_IP' => '1.2.3.4']) === '199.229.67.30');        // falsificado sin Cloudflare
    assert(ip_cliente(['REMOTE_ADDR' => '172.72.0.1', 'HTTP_CF_CONNECTING_IP' => '1.2.3.4']) === '172.72.0.1');              // justo fuera de 172.64.0.0/13
    assert(ip_cliente(['REMOTE_ADDR' => '172.71.170.146', 'HTTP_CF_CONNECTING_IP' => 'basura']) === '172.71.170.146');       // encabezado inválido
    assert(ip_cliente(['REMOTE_ADDR' => '10.0.0.1']) === '10.0.0.1');
    echo "ip ok\n";
}
