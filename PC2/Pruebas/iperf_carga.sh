#!/usr/bin/env bash
# Helper para congestionar la red LAN con iperf3 durante las pruebas GITU.
#
# Esquema: iperf3 servers en PC1 y PC3. Desde PC2 se lanzan clientes hacia
# ambas IPs, saturando los enlaces PC2↔PC1 y PC2↔PC3 que usa GITU.
#
# Uso:
#   ./iperf_carga.sh server                     → correr en PC1 o PC3
#   ./iperf_carga.sh client <IP_PC1> <IP_PC3>   → correr en PC2
#   ./iperf_carga.sh stop                       → matar iperf3 (cualquier PC)
#
# Parámetros configurables (como variables de entorno):
#   RATE=900M DURATION=1200 STREAMS=4 ./iperf_carga.sh client <IP1> <IP3>

set -euo pipefail

RATE="${RATE:-900M}"
DURATION="${DURATION:-1200}"
STREAMS="${STREAMS:-4}"
PIDFILE="/tmp/iperf_carga.pids"

usage() {
    echo ""
    echo "USO: $0 <comando> [args]"
    echo ""
    echo "Comandos:"
    echo "  server                     Levanta iperf3 -s en esta máquina (PC1 o PC3)"
    echo "  client <IP_PC1> <IP_PC3>   Lanza clientes UDP hacia PC1 y PC3 (correr en PC2)"
    echo "  stop                       Mata todos los procesos iperf3 en esta máquina"
    echo ""
    echo "Variables de entorno (con defaults):"
    echo "  RATE=$RATE          Target bandwidth por cliente"
    echo "  DURATION=$DURATION  Duración en segundos (~20 min)"
    echo "  STREAMS=$STREAMS             Streams paralelos por destino"
    echo ""
    echo "Ejemplo completo:"
    echo "  # En PC1:  ./iperf_carga.sh server"
    echo "  # En PC3:  ./iperf_carga.sh server"
    echo "  # En PC2:  RATE=900M DURATION=1200 ./iperf_carga.sh client 192.168.1.10 192.168.1.30"
    echo "  # Al terminar las pruebas:"
    echo "  # En PC2:  ./iperf_carga.sh stop"
    echo "  # En PC1:  ./iperf_carga.sh stop  (o Ctrl+C)"
    echo "  # En PC3:  ./iperf_carga.sh stop  (o Ctrl+C)"
    echo ""
    exit 1
}

cmd_server() {
    echo "[iperf3] Modo servidor — escuchando en puerto 5201..."
    echo "         (Dejar corriendo mientras duren las pruebas; parar con Ctrl+C)"
    iperf3 -s
}

cmd_client() {
    local ip_pc1="$1"
    local ip_pc3="$2"
    echo "[iperf3] Modo cliente desde PC2"
    echo "         PC1 IP : $ip_pc1"
    echo "         PC3 IP : $ip_pc3"
    echo "         Rate   : $RATE por cliente"
    echo "         Streams: $STREAMS por destino"
    echo "         Duración: ${DURATION}s (~$((DURATION / 60)) min)"
    echo ""

    rm -f "$PIDFILE"

    echo "[iperf3] Lanzando cliente → PC1 ($ip_pc1) en background..."
    iperf3 -c "$ip_pc1" -u -b "$RATE" -t "$DURATION" -P "$STREAMS" \
        > /tmp/iperf_pc1.log 2>&1 &
    echo $! >> "$PIDFILE"

    echo "[iperf3] Lanzando cliente → PC3 ($ip_pc3) en background..."
    iperf3 -c "$ip_pc3" -u -b "$RATE" -t "$DURATION" -P "$STREAMS" \
        > /tmp/iperf_pc3.log 2>&1 &
    echo $! >> "$PIDFILE"

    echo ""
    echo "[iperf3] Ambos clientes corriendo en background."
    echo "         PIDs guardados en $PIDFILE"
    echo "         Logs: /tmp/iperf_pc1.log  /tmp/iperf_pc3.log"
    echo ""
    echo "  Verificar que está congestionando (ver throughput):"
    echo "    tail -f /tmp/iperf_pc1.log"
    echo "    tail -f /tmp/iperf_pc3.log"
    echo ""
    echo "  Para parar la congestión:"
    echo "    ./iperf_carga.sh stop"
}

cmd_stop() {
    echo "[iperf3] Deteniendo procesos iperf3..."
    if [ -f "$PIDFILE" ]; then
        while read -r pid; do
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" && echo "  Proceso $pid detenido."
            fi
        done < "$PIDFILE"
        rm -f "$PIDFILE"
    fi
    # Por si quedan procesos residuales
    pkill -f "iperf3" 2>/dev/null && echo "  Procesos iperf3 residuales eliminados." || true
    echo "[iperf3] Listo."
}

# ── Dispatch ──────────────────────────────────────────────────────────────────
if [ $# -eq 0 ]; then
    usage
fi

case "$1" in
    server)
        cmd_server
        ;;
    client)
        if [ $# -lt 3 ]; then
            echo "ERROR: 'client' requiere <IP_PC1> <IP_PC3>"
            usage
        fi
        cmd_client "$2" "$3"
        ;;
    stop)
        cmd_stop
        ;;
    *)
        echo "ERROR: comando desconocido '$1'"
        usage
        ;;
esac
