"""
Generador de carga ZMQ para pruebas de rendimiento GITU.

Publica mensajes JSON validos al broker (puerto 5555) a una tasa configurable,
simulando muchos sensores en paralelo.

Uso:
    python3 generador_carga.py --tasa 1000 --duracion 180
    python3 generador_carga.py --tasa 500 --duracion 60 --intersecciones 8
    python3 generador_carga.py --tasa 5000 --duracion 120 --broker-ip 192.168.1.10
"""

import argparse
import json
import random
import sys
import time
from collections import deque
from datetime import datetime, timedelta

import zmq


INTERSECCIONES_GRILLA = [
    f"INT_{letra}{num}"
    for letra in ("A", "B", "C", "D")
    for num in range(1, 5)
]

NIVELES_CONGESTION = ("BAJA", "MEDIA", "ALTA")


def _ts():
    return datetime.now().isoformat(timespec="milliseconds")


def _msg_camara(interseccion: str, sensor_id: str) -> str:
    evento = {
        "sensor_id": sensor_id,
        "tipo_sensor": "camara",
        "interseccion": interseccion,
        "volumen": random.randint(0, 30),
        "velocidad_promedio": round(random.uniform(5, 60), 1),
        "timestamp": _ts(),
        "cola_horizontal": random.randint(0, 20),
        "cola_vertical": random.randint(0, 20),
    }
    return f"camara {json.dumps(evento)}"


def _msg_gps(interseccion: str, sensor_id: str) -> str:
    evento = {
        "sensor_id": sensor_id,
        "tipo_sensor": "gps",
        "interseccion": interseccion,
        "nivel_congestion": random.choice(NIVELES_CONGESTION),
        "velocidad_promedio": round(random.uniform(5, 60), 1),
        "timestamp": _ts(),
    }
    return f"gps {json.dumps(evento)}"


def _msg_espira(interseccion: str, sensor_id: str) -> str:
    inicio = datetime.now()
    fin = inicio + timedelta(seconds=30)
    evento = {
        "sensor_id": sensor_id,
        "tipo_sensor": "espira_inductiva",
        "interseccion": interseccion,
        "vehiculos_contados": random.randint(0, 120),
        "intervalo_segundos": 30,
        "timestamp_inicio": inicio.isoformat(timespec="milliseconds"),
        "timestamp_fin": fin.isoformat(timespec="milliseconds"),
    }
    return f"espira_inductiva {json.dumps(evento)}"


_GENERADORES = (_msg_camara, _msg_gps, _msg_espira)


def generar_mensajes(socket: zmq.Socket, intersecciones: list, tasa: int, duracion: int):
    """Publica mensajes a la tasa pedida durante `duracion` segundos."""
    t_inicio = time.monotonic()
    t_fin = t_inicio + duracion
    intervalo = 1.0 / tasa  # segundos entre mensajes

    # Contadores para reporte cada 5s
    t_ultimo_reporte = t_inicio
    msgs_en_ventana = 0

    # Rotar tipo de sensor y interseccion de forma determinista
    idx_tipo = 0
    idx_int = 0
    n_tipos = len(_GENERADORES)
    n_ints = len(intersecciones)

    print(f"[GENERADOR] Iniciando: tasa={tasa} msg/s | duracion={duracion}s | intersecciones={n_ints}")
    print(f"[GENERADOR] Conectado al broker. Publicando...")

    t_sig = time.monotonic()

    while True:
        ahora = time.monotonic()
        if ahora >= t_fin:
            break

        # Esperar hasta el siguiente slot de tiempo
        if t_sig > ahora:
            time.sleep(t_sig - ahora)

        t_sig += intervalo

        interseccion = intersecciones[idx_int % n_ints]
        tipo_idx = idx_tipo % n_tipos
        sensor_id = f"GEN-{interseccion}-{('CAM', 'GPS', 'ESP')[tipo_idx]}"

        mensaje = _GENERADORES[tipo_idx](interseccion, sensor_id)
        try:
            socket.send_string(mensaje, zmq.NOBLOCK)
        except zmq.Again:
            pass

        msgs_en_ventana += 1
        idx_tipo += 1
        idx_int += 1

        # Reporte cada 5 segundos
        ahora = time.monotonic()
        if ahora - t_ultimo_reporte >= 5.0:
            elapsed = ahora - t_ultimo_reporte
            tasa_real = msgs_en_ventana / elapsed
            restante = max(0, t_fin - ahora)
            print(f"[GENERADOR] Tasa real: {tasa_real:.0f} msg/s | "
                  f"Enviados: {msgs_en_ventana} en {elapsed:.1f}s | "
                  f"Restante: {restante:.0f}s")
            t_ultimo_reporte = ahora
            msgs_en_ventana = 0

    print(f"[GENERADOR] Terminado. Duracion total: {time.monotonic() - t_inicio:.1f}s")


def main():
    parser = argparse.ArgumentParser(
        description="Generador de carga ZMQ para pruebas GITU"
    )
    parser.add_argument("--tasa", type=int, default=1000,
                        help="Mensajes por segundo (default: 1000)")
    parser.add_argument("--duracion", type=int, default=180,
                        help="Duracion en segundos (default: 180)")
    parser.add_argument("--intersecciones", type=int, default=16,
                        help="Numero de intersecciones a simular 1-16 (default: 16)")
    parser.add_argument("--broker-ip", default="127.0.0.1",
                        help="IP del broker (default: 127.0.0.1)")
    args = parser.parse_args()

    if args.tasa < 1:
        print("ERROR: --tasa debe ser >= 1")
        sys.exit(1)
    if args.duracion < 1:
        print("ERROR: --duracion debe ser >= 1")
        sys.exit(1)
    n_ints = max(1, min(args.intersecciones, len(INTERSECCIONES_GRILLA)))
    intersecciones = INTERSECCIONES_GRILLA[:n_ints]

    ctx = zmq.Context()
    sock = ctx.socket(zmq.PUB)
    sock.setsockopt(zmq.SNDHWM, 10000)
    sock.connect(f"tcp://{args.broker_ip}:5555")

    # Pausa inicial para que ZMQ establezca la conexion (slow joiner syndrome)
    time.sleep(0.5)

    try:
        generar_mensajes(sock, intersecciones, args.tasa, args.duracion)
    except KeyboardInterrupt:
        print("\n[GENERADOR] Interrumpido por el usuario")
    finally:
        sock.close()
        ctx.term()


if __name__ == "__main__":
    main()
