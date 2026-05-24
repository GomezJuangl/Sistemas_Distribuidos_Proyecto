#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════
#  PC2 (10.43.99.102) — BD Réplica + Analítica + Control + Medición
#  Uso: ./pc2_caso.sh <escenario> <diseno>
#  Ejemplo: ./pc2_caso.sh A original
#           ./pc2_caso.sh A multihilo_4
#           ./pc2_caso.sh B multihilo_16
#
#  ORDEN DE EJECUCIÓN:
#    1. Primero ejecutar pc3_servicios.sh en PC3
#    2. Luego ejecutar pc1_servicios.sh <hilos> <escenario> en PC1
#    3. Por último ejecutar este script en PC2
# ═══════════════════════════════════════════════════════════════

if [[ $# -lt 2 ]]; then
  echo "Uso: $0 <escenario> <diseno>"
  echo "  escenario: A o B"
  echo "  diseno:    original, multihilo_4, multihilo_8, multihilo_16, multihilo_32, multihilo_64"
  exit 1
fi

ESCENARIO="$1"
DISENO="$2"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=python3

# ─── Limpiar procesos anteriores ──────────────────────────────
echo "[PC2] Limpiando procesos anteriores..."
pkill -f "BaseDatos_Replica.py" 2>/dev/null || true
pkill -f "servicio_analitica.py" 2>/dev/null || true
pkill -f "servicio_control_semaforos.py" 2>/dev/null || true
pkill -f "medir_rendimiento.py" 2>/dev/null || true
sleep 2
pkill -9 -f "BaseDatos_Replica.py" 2>/dev/null || true
pkill -9 -f "servicio_analitica.py" 2>/dev/null || true
pkill -9 -f "servicio_control_semaforos.py" 2>/dev/null || true
pkill -9 -f "medir_rendimiento.py" 2>/dev/null || true

if command -v fuser >/dev/null 2>&1; then
  for p in 5102 6001 6002 7002; do fuser -k "${p}/tcp" 2>/dev/null || true; done
fi
sleep 2

# ─── Limpiar BD réplica y log VD2 ─────────────────────────────
rm -f "$ROOT_DIR/BaseDatosReplica/bd_replica.db"
> "$ROOT_DIR/Pruebas/vd2_fin.log" 2>/dev/null || true

echo "[PC2] Iniciando caso: Escenario $ESCENARIO | Diseño $DISENO"
echo ""

# ─── 1. BD Réplica ───────────────────────────────────────────
echo "[PC2] Levantando BD Réplica..."
(cd "$ROOT_DIR/BaseDatosReplica" && $PY -u BaseDatos_Replica.py > /dev/null 2>&1) &
PID_BDR=$!
sleep 2

# ─── 2. Control Semáforos ─────────────────────────────────────
echo "[PC2] Levantando Control Semáforos..."
(cd "$ROOT_DIR" && $PY -u servicio_control_semaforos.py > /dev/null 2>&1) &
PID_CTRL=$!
sleep 1

# ─── 3. Analítica ────────────────────────────────────────────
echo "[PC2] Levantando Analítica..."
(cd "$ROOT_DIR" && $PY -u servicio_analitica.py > /dev/null 2>&1) &
PID_ANA=$!
sleep 3

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  PC2 SERVICIOS LISTOS"
echo "  BD Réplica PID: $PID_BDR"
echo "  Control PID:    $PID_CTRL"
echo "  Analítica PID:  $PID_ANA"
echo "════════════════════════════════════════════════════════════"
echo ""

# ─── 4. Warmup ───────────────────────────────────────────────
echo "[PC2] Warmup 25s (esperando que PC1 y PC3 estén estables)..."
sleep 25

# ─── 5. Medir ────────────────────────────────────────────────
echo "[PC2] Iniciando medición: Escenario=$ESCENARIO Diseño=$DISENO"
echo "       Esto tarda ~8 minutos..."
echo ""
(cd "$ROOT_DIR/Pruebas" && $PY -u medir_rendimiento.py \
  --escenario "$ESCENARIO" --diseno "$DISENO")

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  MEDICIÓN COMPLETADA"
echo "  Resultados en: PC2/Pruebas/resultados.csv"
echo "════════════════════════════════════════════════════════════"

# ─── 6. Detener servicios de PC2 ─────────────────────────────
echo "[PC2] Deteniendo servicios..."
kill $PID_BDR $PID_CTRL $PID_ANA 2>/dev/null || true
pkill -f "BaseDatos_Replica.py\|servicio_analitica.py\|servicio_control_semaforos.py" 2>/dev/null || true
sleep 1

echo "[PC2] Listo. Ahora haz Ctrl+C en PC1 y PC3."
echo ""
