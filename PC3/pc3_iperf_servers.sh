#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  PC3 — Servidores iperf3 (8 procesos en puertos 5401-5408)
#  Uso: ./pc3_iperf_servers.sh
#       ./pc3_iperf_servers.sh stop
# ═══════════════════════════════════════════════════════════════

if [[ "${1:-}" == "stop" ]]; then
  echo "[PC3] Deteniendo servidores iperf3..."
  pkill -f "iperf3" 2>/dev/null || true
  echo "[PC3] Detenidos."
  exit 0
fi

echo "[PC3] Deteniendo iperf3 anteriores..."
pkill -f "iperf3" 2>/dev/null || true
sleep 1

echo "[PC3] Levantando 8 servidores iperf3 (puertos 5401-5408)..."
for PORT in 5401 5402 5403 5404 5405 5406 5407 5408; do
  iperf3 -s -p "$PORT" -D
done

echo "[PC3] 8 servidores iperf3 listos."
echo "  Puertos: 5401-5408"
echo "  Para detener: ./pc3_iperf_servers.sh stop"
