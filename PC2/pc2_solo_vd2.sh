#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════
#  PC2 — Solo medición VD2 (sin iperf3, red limpia)
#  Uso: ./pc2_solo_vd2.sh <escenario> <diseno>
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

echo "[PC2] Limpiando procesos anteriores..."
pkill -f "BaseDatos_Replica.py" 2>/dev/null || true
pkill -f "servicio_analitica.py" 2>/dev/null || true
pkill -f "servicio_control_semaforos.py" 2>/dev/null || true
pkill -f "medir_rendimiento.py" 2>/dev/null || true
sleep 2
pkill -9 -f "BaseDatos_Replica.py" 2>/dev/null || true
pkill -9 -f "servicio_analitica.py" 2>/dev/null || true
pkill -9 -f "servicio_control_semaforos.py" 2>/dev/null || true

if command -v fuser >/dev/null 2>&1; then
  for p in 5102 6001 6002 7002; do fuser -k "${p}/tcp" 2>/dev/null || true; done
fi
sleep 2

rm -f "$ROOT_DIR/BaseDatosReplica/bd_replica.db"
> "$ROOT_DIR/Pruebas/vd2_fin.log" 2>/dev/null || true

echo "[PC2] Caso VD2: Escenario $ESCENARIO | Diseño $DISENO | Red LIMPIA"
echo ""

(cd "$ROOT_DIR/BaseDatosReplica" && $PY -u BaseDatos_Replica.py > /dev/null 2>&1) &
sleep 2
(cd "$ROOT_DIR" && $PY -u servicio_control_semaforos.py > /dev/null 2>&1) &
sleep 1
(cd "$ROOT_DIR" && $PY -u servicio_analitica.py > /dev/null 2>&1) &
sleep 3

echo "[PC2] Warmup 15s..."
sleep 15

echo "[PC2] Midiendo VD2 (solo-vd2, red limpia)..."
echo ""
(cd "$ROOT_DIR/Pruebas" && $PY -u medir_rendimiento.py \
  --escenario "$ESCENARIO" --diseno "$DISENO" --solo-vd2 --red limpia)

echo ""
echo "[PC2] Deteniendo servicios..."
pkill -f "BaseDatos_Replica.py\|servicio_analitica.py\|servicio_control_semaforos.py" 2>/dev/null || true
sleep 1

echo "[PC2] Listo. Haz Ctrl+C en PC1 y PC3."
