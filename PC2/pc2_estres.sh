#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════
#  PC2 (10.43.99.102) — BD Réplica + Analítica + Control + Prueba de estrés
#  Para prueba de estrés (carga máxima del sistema)
#
#  Uso: ./pc2_estres.sh
#       ./pc2_estres.sh "50,100,200,500,1000,2000,5000"
#       ./pc2_estres.sh "50,100,500,1000" 90
#
#  Args:
#    $1 = tasas separadas por coma (default: 50,100,200,500,1000,2000,5000)
#    $2 = ventana en segundos por tasa (default: 60)
#
#  ORDEN DE EJECUCIÓN:
#    1. PC3: ./pc3_servicios.sh
#    2. PC1: ./pc1_estres.sh
#    3. PC2: ./pc2_estres.sh   (este script)
# ═══════════════════════════════════════════════════════════════

TASAS="${1:-50,100,200,500,1000,2000,5000}"
VENTANA="${2:-60}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=python3

# ─── Limpiar procesos anteriores ──────────────────────────────
echo "[PC2-ESTRES] Limpiando procesos anteriores..."
pkill -f "BaseDatos_Replica.py" 2>/dev/null || true
pkill -f "servicio_analitica.py" 2>/dev/null || true
pkill -f "servicio_control_semaforos.py" 2>/dev/null || true
pkill -f "prueba_estres_cpu.py" 2>/dev/null || true
pkill -f "medir_rendimiento.py" 2>/dev/null || true
sleep 2
pkill -9 -f "BaseDatos_Replica.py" 2>/dev/null || true
pkill -9 -f "servicio_analitica.py" 2>/dev/null || true
pkill -9 -f "servicio_control_semaforos.py" 2>/dev/null || true
pkill -9 -f "prueba_estres_cpu.py" 2>/dev/null || true
pkill -9 -f "medir_rendimiento.py" 2>/dev/null || true

if command -v fuser >/dev/null 2>&1; then
  for p in 5102 6001 6002 7002; do fuser -k "${p}/tcp" 2>/dev/null || true; done
fi
sleep 2

# ─── Limpiar BD réplica ───────────────────────────────────────
rm -f "$ROOT_DIR/BaseDatosReplica/bd_replica.db"
> "$ROOT_DIR/Pruebas/vd2_fin.log" 2>/dev/null || true

echo "[PC2-ESTRES] Prueba de estrés | Tasas: $TASAS | Ventana: ${VENTANA}s"
echo ""

# ─── 1. BD Réplica ───────────────────────────────────────────
echo "[PC2-ESTRES] Levantando BD Réplica..."
(cd "$ROOT_DIR/BaseDatosReplica" && $PY -u BaseDatos_Replica.py > /dev/null 2>&1) &
PID_BDR=$!
sleep 2

# ─── 2. Control Semáforos ─────────────────────────────────────
echo "[PC2-ESTRES] Levantando Control Semáforos..."
(cd "$ROOT_DIR" && $PY -u servicio_control_semaforos.py > /dev/null 2>&1) &
PID_CTRL=$!
sleep 1

# ─── 3. Analítica ────────────────────────────────────────────
echo "[PC2-ESTRES] Levantando Analítica..."
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
echo "[PC2-ESTRES] Warmup 15s..."
sleep 15

# ─── 5. Prueba de estrés ─────────────────────────────────────
echo "[PC2-ESTRES] Iniciando prueba de estrés..."
echo ""
(cd "$ROOT_DIR/Pruebas" && $PY -u prueba_estres_cpu.py \
  --tasas "$TASAS" --ventana "$VENTANA")

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  PRUEBA DE ESTRÉS COMPLETADA"
echo "  Resultados: PC2/Pruebas/estres_resultados.csv"
echo "  Gráfica:    PC2/Pruebas/graficas/estres_carga_maxima.png"
echo "════════════════════════════════════════════════════════════"

# ─── 6. Detener servicios ────────────────────────────────────
echo "[PC2-ESTRES] Deteniendo servicios..."
kill $PID_BDR $PID_CTRL $PID_ANA 2>/dev/null || true
pkill -f "BaseDatos_Replica.py\|servicio_analitica.py\|servicio_control_semaforos.py" 2>/dev/null || true
sleep 1

echo "[PC2-ESTRES] Listo. Ahora haz Ctrl+C en PC1 y PC3."
echo ""
