#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  PC1 — Servidores iperf3 (8 procesos en puertos 5301-5308)
#  Uso: ./pc1_iperf_servers.sh
#       ./pc1_iperf_servers.sh stop
# ═══════════════════════════════════════════════════════════════

if [[ "${1:-}" == "stop" ]]; then
  echo "[PC1] Deteniendo servidores iperf3..."
  pkill -f "iperf3" 2>/dev/null || true
  echo "[PC1] Detenidos."
  exit 0
fi

echo "[PC1] Deteniendo iperf3 anteriores..."
pkill -f "iperf3" 2>/dev/null || true
sleep 1

echo "[PC1] Levantando 8 servidores iperf3 (puertos 5301-5308)..."
for PORT in 5301 5302 5303 5304 5305 5306 5307 5308; do
  iperf3 -s -p "$PORT" -D
done

echo "[PC1] 8 servidores iperf3 listos."
echo "  Puertos: 5301-5308"
echo "  Para detener: ./pc1_iperf_servers.sh stop"
