#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════
#  PC1 — SIN generador de carga (solo para mediciones VD2)
#  Uso: ./pc1_solo_vd2.sh <hilos> <escenario>
# ═══════════════════════════════════════════════════════════════

if [[ $# -lt 2 ]]; then
  echo "Uso: $0 <hilos> <escenario>"
  echo "  hilos:     1, 4, 16, 32"
  echo "  escenario: A o B"
  exit 1
fi

HILOS="$1"
ESCENARIO="$2"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=python3

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

rm -rf "$ROOT_DIR/Broker/broker_audit/"
ulimit -n 4096 2>/dev/null || true

echo "[PC1] Iniciando SIN generador: Escenario $ESCENARIO | $HILOS hilos"
echo ""

echo "[PC1] Levantando Broker ($HILOS hilos)..."
(cd "$ROOT_DIR/Broker" && BROKER_WORKERS="$HILOS" $PY -u Broker_multihilo.py > /dev/null 2>&1) &
PID_BROKER=$!
sleep 3

echo "[PC1] Levantando Simulación (escenario $ESCENARIO)..."
(cd "$ROOT_DIR" && $PY -u main.py --escenario "$ESCENARIO" > /dev/null 2>&1) &
PID_MAIN=$!

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  PC1 LISTO (SIN generador) — Escenario $ESCENARIO | $HILOS hilos"
echo "  Broker PID: $PID_BROKER"
echo "  Main PID:   $PID_MAIN"
echo ""
echo "  Presiona Ctrl+C para detener todo"
echo "════════════════════════════════════════════════════════════"

trap "echo '[PC1] Deteniendo...'; kill $PID_BROKER $PID_MAIN 2>/dev/null; pkill -f 'Broker\|main.py\|receptor_control' 2>/dev/null; echo '[PC1] Detenido.'; exit 0" INT TERM

wait
