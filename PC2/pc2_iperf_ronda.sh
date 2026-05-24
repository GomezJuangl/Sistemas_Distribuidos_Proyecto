#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════
#  PC2 — Medición VD2 con red congestionada (iperf3 multi-proceso TCP)
#
#  ANTES DE EJECUTAR:
#    PC1: ./pc1_iperf_servers.sh  (levanta 8 servidores iperf3)
#    PC3: ./pc3_iperf_servers.sh  (levanta 8 servidores iperf3)
#
#  Uso: ./pc2_iperf_ronda.sh <escenario> <diseno>
# ═══════════════════════════════════════════════════════════════

if [[ $# -lt 2 ]]; then
  echo "Uso: $0 <escenario> <diseno>"
  echo "  escenario: A o B"
  echo "  diseno:    original, multihilo_4, multihilo_16, multihilo_32"
  exit 1
fi

ESCENARIO="$1"
DISENO="$2"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=python3

IP_PC1="10.43.99.110"
IP_PC3="10.43.100.49"
IPERF_DURATION=300

# ─── Limpiar procesos anteriores ──────────────────────────────
echo "[PC2] Limpiando procesos anteriores..."
pkill -f "BaseDatos_Replica.py" 2>/dev/null || true
pkill -f "servicio_analitica.py" 2>/dev/null || true
pkill -f "servicio_control_semaforos.py" 2>/dev/null || true
pkill -f "medir_rendimiento.py" 2>/dev/null || true
pkill -f "iperf3" 2>/dev/null || true
sleep 2
pkill -9 -f "BaseDatos_Replica.py" 2>/dev/null || true
pkill -9 -f "servicio_analitica.py" 2>/dev/null || true
pkill -9 -f "servicio_control_semaforos.py" 2>/dev/null || true
pkill -9 -f "iperf3" 2>/dev/null || true

if command -v fuser >/dev/null 2>&1; then
  for p in 5102 6001 6002 7002; do fuser -k "${p}/tcp" 2>/dev/null || true; done
fi
sleep 2

# ─── Limpiar BD réplica ───────────────────────────────────────
rm -f "$ROOT_DIR/BaseDatosReplica/bd_replica.db"
> "$ROOT_DIR/Pruebas/vd2_fin.log" 2>/dev/null || true

echo "[PC2-IPERF] Caso: Escenario $ESCENARIO | Diseno $DISENO | Red CONGESTIONADA"
echo ""

# ─── 1. Servicios base PC2 ───────────────────────────────────
echo "[PC2] Levantando BD Replica..."
(cd "$ROOT_DIR/BaseDatosReplica" && $PY -u BaseDatos_Replica.py > /dev/null 2>&1) &
sleep 2

echo "[PC2] Levantando Control Semaforos..."
(cd "$ROOT_DIR" && $PY -u servicio_control_semaforos.py > /dev/null 2>&1) &
sleep 1

echo "[PC2] Levantando Analitica..."
(cd "$ROOT_DIR" && $PY -u servicio_analitica.py > /dev/null 2>&1) &
sleep 3

# ─── 2. Lanzar clientes iperf3 TCP (8 hacia PC1 + 8 hacia PC3) ──
echo "[PC2] Lanzando 16 clientes iperf3 TCP (8 hacia PC1 + 8 hacia PC3)..."
echo "       Esto satura la red de 10Gbps con trafico TCP real."

# 8 clientes hacia PC1 (puertos 5301-5308)
for PORT in 5301 5302 5303 5304 5305 5306 5307 5308; do
  iperf3 -c "$IP_PC1" -p "$PORT" -t "$IPERF_DURATION" > /dev/null 2>&1 &
done

# 8 clientes hacia PC3 (puertos 5401-5408)
for PORT in 5401 5402 5403 5404 5405 5406 5407 5408; do
  iperf3 -c "$IP_PC3" -p "$PORT" -t "$IPERF_DURATION" > /dev/null 2>&1 &
done

echo "[PC2] 16 clientes iperf3 lanzados."
sleep 10

# Verificar que hay congestion
echo "[PC2] Verificando congestion (ping a PC1)..."
ping -c 3 -q "$IP_PC1" | tail -1

# ─── 3. Warmup ────────────────────────────────────────────────
echo "[PC2] Warmup 10s..."
sleep 10

# ─── 4. Medir solo VD2 ───────────────────────────────────────
echo "[PC2] Midiendo VD2 (solo-vd2, red congestionada)..."
echo ""
(cd "$ROOT_DIR/Pruebas" && $PY -u medir_rendimiento.py \
  --escenario "$ESCENARIO" --diseno "$DISENO" --solo-vd2 --red congestionada)

# ─── 5. Detener iperf3 y servicios ────────────────────────────
echo ""
echo "[PC2] Deteniendo iperf3 y servicios..."
pkill -f "iperf3" 2>/dev/null || true
pkill -f "BaseDatos_Replica.py\|servicio_analitica.py\|servicio_control_semaforos.py" 2>/dev/null || true
sleep 1

echo "[PC2] Listo. Haz Ctrl+C en PC1 y PC3 (servicios GITU)."
echo "       En PC1: ./pc1_iperf_servers.sh stop"
echo "       En PC3: ./pc3_iperf_servers.sh stop"
echo ""
