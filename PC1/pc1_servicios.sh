#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════
#  PC1 (10.43.99.110) — Broker + Simulación + Generador de carga
#  Uso: ./pc1_servicios.sh <hilos> <escenario>
#  Ejemplo: ./pc1_servicios.sh 4 A
#           ./pc1_servicios.sh 1 B    (1 = original/monohilo)
# ═══════════════════════════════════════════════════════════════

if [[ $# -lt 2 ]]; then
  echo "Uso: $0 <hilos> <escenario>"
  echo "  hilos:     1, 4, 8, 16, 32, 64"
  echo "  escenario: A o B"
  exit 1
fi

HILOS="$1"
ESCENARIO="$2"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=python3
TASA_GENERADOR=1000
DURACION_GENERADOR=900

# ─── Limpiar procesos anteriores ──────────────────────────────
echo "[PC1] Limpiando procesos anteriores..."
pkill -f "Broker.py" 2>/dev/null || true
pkill -f "Broker_multihilo.py" 2>/dev/null || true
pkill -f "main.py" 2>/dev/null || true
pkill -f "generador_carga.py" 2>/dev/null || true
pkill -f "receptor_control_semaforos.py" 2>/dev/null || true
sleep 2
pkill -9 -f "Broker.py" 2>/dev/null || true
pkill -9 -f "Broker_multihilo.py" 2>/dev/null || true
pkill -9 -f "main.py" 2>/dev/null || true
pkill -9 -f "generador_carga.py" 2>/dev/null || true
pkill -9 -f "receptor_control_semaforos.py" 2>/dev/null || true

if command -v fuser >/dev/null 2>&1; then
  for p in 5555 5556 6003; do fuser -k "${p}/tcp" 2>/dev/null || true; done
fi
sleep 2

# ─── Limpiar audit ────────────────────────────────────────────
rm -rf "$ROOT_DIR/Broker/broker_audit/"

ulimit -n 4096 2>/dev/null || true

echo "[PC1] Iniciando caso: Escenario $ESCENARIO | $HILOS hilos"
echo ""

# ─── 1. Broker ────────────────────────────────────────────────
echo "[PC1] Levantando Broker ($HILOS hilos)..."
(cd "$ROOT_DIR/Broker" && BROKER_WORKERS="$HILOS" $PY -u Broker_multihilo.py) &
PID_BROKER=$!
sleep 3

# ─── 2. Simulación ────────────────────────────────────────────
echo "[PC1] Levantando Simulación (escenario $ESCENARIO)..."
(cd "$ROOT_DIR" && $PY -u main.py --escenario "$ESCENARIO") &
PID_MAIN=$!
sleep 2

# ─── 3. Generador de carga ────────────────────────────────────
echo "[PC1] Levantando Generador de carga (tasa=$TASA_GENERADOR, duracion=$DURACION_GENERADOR)..."
(cd "$ROOT_DIR" && $PY -u generador_carga.py --tasa "$TASA_GENERADOR" --duracion "$DURACION_GENERADOR") &
PID_GEN=$!

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  PC1 LISTO — Escenario $ESCENARIO | $HILOS hilos"
echo "  Broker PID: $PID_BROKER"
echo "  Main PID:   $PID_MAIN"
echo "  Generador PID: $PID_GEN"
echo ""
echo "  Presiona Ctrl+C para detener todo"
echo "════════════════════════════════════════════════════════════"

# Esperar a que el usuario haga Ctrl+C
trap "echo '[PC1] Deteniendo...'; kill $PID_BROKER $PID_MAIN $PID_GEN 2>/dev/null; pkill -f 'Broker\|main.py\|generador_carga\|receptor_control' 2>/dev/null; echo '[PC1] Detenido.'; exit 0" INT TERM

wait
