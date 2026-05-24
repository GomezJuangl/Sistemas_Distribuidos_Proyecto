#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════
#  PC3 (10.43.100.49) — BD Principal + Monitoreo + Disparador VD2
#  Uso: ./pc3_servicios.sh
#  (No cambia entre casos, siempre se levanta igual)
# ═══════════════════════════════════════════════════════════════

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=python3

# ─── Limpiar procesos anteriores ──────────────────────────────
echo "[PC3] Limpiando procesos anteriores..."
pkill -f "BaseDatos.py" 2>/dev/null || true
pkill -f "Monitoreo_Consulta.py" 2>/dev/null || true
pkill -f "disparador_vd2.py" 2>/dev/null || true
sleep 2
pkill -9 -f "BaseDatos.py" 2>/dev/null || true
pkill -9 -f "Monitoreo_Consulta.py" 2>/dev/null || true
pkill -9 -f "disparador_vd2.py" 2>/dev/null || true

if command -v fuser >/dev/null 2>&1; then
  for p in 5101 6004 7001 7003 7004; do fuser -k "${p}/tcp" 2>/dev/null || true; done
fi
sleep 2

# ─── Limpiar BD ───────────────────────────────────────────────
rm -f "$ROOT_DIR/BaseDatosPrincipal/bd_principal.db"

echo "[PC3] Iniciando servicios..."
echo ""

# ─── 1. BD Principal ─────────────────────────────────────────
echo "[PC3] Levantando BD Principal..."
(cd "$ROOT_DIR/BaseDatosPrincipal" && $PY -u BaseDatos.py) &
PID_BD=$!
sleep 2

# ─── 2. Monitoreo ────────────────────────────────────────────
echo "[PC3] Levantando Monitoreo..."
(cd "$ROOT_DIR" && $PY -u Monitoreo_Consulta.py) &
PID_MON=$!
sleep 1

# ─── 3. Disparador VD2 ───────────────────────────────────────
echo "[PC3] Levantando Disparador VD2..."
(cd "$ROOT_DIR" && $PY -u disparador_vd2.py) &
PID_DISP=$!

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  PC3 LISTO"
echo "  BD Principal PID: $PID_BD"
echo "  Monitoreo PID:    $PID_MON"
echo "  Disparador PID:   $PID_DISP"
echo ""
echo "  Presiona Ctrl+C para detener todo"
echo "════════════════════════════════════════════════════════════"

trap "echo '[PC3] Deteniendo...'; kill $PID_BD $PID_MON $PID_DISP 2>/dev/null; pkill -f 'BaseDatos.py\|Monitoreo\|disparador' 2>/dev/null; echo '[PC3] Detenido.'; exit 0" INT TERM

wait
