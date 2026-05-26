#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════
#  PC1 (10.43.99.110) — Broker 8 hilos + Generador controlable
#  Para prueba de estrés (carga máxima del sistema)
#
#  Uso: ./pc1_estres.sh
#       ./pc1_estres.sh 8          (hilos, default 8)
#       ./pc1_estres.sh 8 A        (hilos + escenario, default A)
#
#  ORDEN DE EJECUCIÓN:
#    1. PC3: ./pc3_servicios.sh
#    2. PC1: ./pc1_estres.sh
#    3. PC2: ./pc2_estres.sh
# ═══════════════════════════════════════════════════════════════

HILOS="${1:-8}"
ESCENARIO="${2:-A}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=python3

# ─── Limpiar procesos anteriores ──────────────────────────────
echo "[PC1-ESTRES] Limpiando procesos anteriores..."
pkill -f "Broker.py" 2>/dev/null || true
pkill -f "Broker_multihilo.py" 2>/dev/null || true
pkill -f "main.py" 2>/dev/null || true
pkill -f "generador_carga" 2>/dev/null || true
pkill -f "receptor_control_semaforos.py" 2>/dev/null || true
sleep 2
pkill -9 -f "Broker.py" 2>/dev/null || true
pkill -9 -f "Broker_multihilo.py" 2>/dev/null || true
pkill -9 -f "main.py" 2>/dev/null || true
pkill -9 -f "generador_carga" 2>/dev/null || true
pkill -9 -f "receptor_control_semaforos.py" 2>/dev/null || true

if command -v fuser >/dev/null 2>&1; then
  for p in 5555 5556 6003 6010; do fuser -k "${p}/tcp" 2>/dev/null || true; done
fi
sleep 2

# ─── Limpiar audit ────────────────────────────────────────────
rm -rf "$ROOT_DIR/Broker/broker_audit/"

ulimit -n 4096 2>/dev/null || true

echo "[PC1-ESTRES] Prueba de estrés: $HILOS hilos | Escenario $ESCENARIO"
echo ""

# ─── 1. Broker ────────────────────────────────────────────────
echo "[PC1-ESTRES] Levantando Broker ($HILOS hilos)..."
(cd "$ROOT_DIR/Broker" && BROKER_WORKERS="$HILOS" $PY -u Broker_multihilo.py) &
PID_BROKER=$!
sleep 3

# ─── 2. Simulación ────────────────────────────────────────────
echo "[PC1-ESTRES] Levantando Simulación (escenario $ESCENARIO)..."
(cd "$ROOT_DIR" && $PY -u main.py --escenario "$ESCENARIO") &
PID_MAIN=$!
sleep 2

# ─── 3. Generador controlable ────────────────────────────────
echo "[PC1-ESTRES] Levantando Generador de carga controlable (puerto 6010)..."
(cd "$ROOT_DIR" && $PY -u generador_carga_estres.py --broker-ip 127.0.0.1 --puerto-control 6010) &
PID_GEN=$!

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  PC1 LISTO — PRUEBA DE ESTRÉS"
echo "  Broker PID:    $PID_BROKER ($HILOS hilos)"
echo "  Main PID:      $PID_MAIN (escenario $ESCENARIO)"
echo "  Generador PID: $PID_GEN (controlable, puerto 6010)"
echo ""
echo "  Esperando comandos de PC2..."
echo "  Presiona Ctrl+C para detener todo"
echo "════════════════════════════════════════════════════════════"

trap "echo '[PC1-ESTRES] Deteniendo...'; kill $PID_BROKER $PID_MAIN $PID_GEN 2>/dev/null; pkill -f 'Broker\|main.py\|generador_carga\|receptor_control' 2>/dev/null; echo '[PC1-ESTRES] Detenido.'; exit 0" INT TERM

wait
