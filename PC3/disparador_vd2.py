"""
Disparador VD2 — corre en PC3.

medir_rendimiento.py (PC2) le envía los parámetros del comando de prioridad;
este proceso captura t0 justo antes de mandar el REQ a analítica (PC2:6001),
y devuelve ts_inicio a PC2 para que compute la latencia correctamente.

El t0 se origina aquí, en PC3, simulando el momento exacto en que el
usuario del Monitoreo envía la solicitud. Equivale a la línea 193-194 de
Monitoreo_Consulta.py, pero automatizado para el script de medición.
"""

import json
import zmq
from datetime import datetime

# ─── CONFIGURACIÓN ────────────────────────────────────────────────────────────
ESCUCHA_PUERTO   = 6004          # REP que escucha peticiones de PC2
ANALITICA_IP     = "127.0.0.1"  # IP de PC2 donde vive servicio_analitica.py
ANALITICA_PUERTO = 6001
TIMEOUT_RECV_MS  = 8000         # timeout esperando respuesta de analítica
# ──────────────────────────────────────────────────────────────────────────────


def main():
    ctx = zmq.Context()

    # REP: recibe solicitudes de PC2 (medir_rendimiento.py)
    rep = ctx.socket(zmq.REP)
    rep.bind(f"tcp://*:{ESCUCHA_PUERTO}")
    print(f"[DISPARADOR-VD2] Escuchando en tcp://*:{ESCUCHA_PUERTO}")

    while True:
        try:
            msg = rep.recv_string()
            params = json.loads(msg)
        except Exception as e:
            rep.send_string(json.dumps({"error": f"Mensaje inválido: {e}"}))
            continue

        # Crear socket REQ a analítica (uno por medición — patrón seguro para ZMQ REQ)
        req = ctx.socket(zmq.REQ)
        req.setsockopt(zmq.RCVTIMEO, TIMEOUT_RECV_MS)
        req.setsockopt(zmq.LINGER, 0)
        req.connect(f"tcp://{ANALITICA_IP}:{ANALITICA_PUERTO}")

        # t0 capturado en PC3, justo antes del send — este es el momento del "usuario"
        ts_inicio = datetime.now().isoformat(timespec="milliseconds")
        print(f"[VD2-INICIO] {ts_inicio} — comando enviado a analítica desde PC3")

        cmd = json.dumps({
            "tipo":         params.get("tipo", "prioridad"),
            "interseccion": params.get("interseccion", "INT_A1"),
            "eje":          params.get("eje", "H"),
            "duracion":     params.get("duracion", 15),
        })

        try:
            req.send_string(cmd)
            respuesta = req.recv_string()
        except zmq.Again:
            respuesta = "TIMEOUT"
            print("[DISPARADOR-VD2] Sin respuesta de analítica (timeout)")
        finally:
            req.close()

        rep.send_string(json.dumps({
            "ts_inicio": ts_inicio,
            "respuesta_analitica": respuesta,
        }))


if __name__ == "__main__":
    main()
