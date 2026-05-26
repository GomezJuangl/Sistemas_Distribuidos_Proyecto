"""
Generador de carga controlable para prueba de estrés GITU.

A diferencia de generador_carga.py (que corre con tasa fija), este generador
escucha comandos por un socket ZMQ REP (puerto 6010) para que el script de
prueba en PC2 pueda:
  - Iniciar generación a una tasa específica
  - Parar la generación
  - Consultar cuántos mensajes envió en la última ronda

Uso:
    python3 generador_carga_estres.py
    python3 generador_carga_estres.py --broker-ip 127.0.0.1 --puerto-control 6010

Comandos JSON que acepta por el socket REP (puerto 6010):
    {"accion": "iniciar", "tasa": 1000, "duracion": 65}
    {"accion": "parar"}
    {"accion": "stats"}
"""

import argparse
import json
import random
import sys
import threading
import time
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


def _msg_camara(interseccion, sensor_id):
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


def _msg_gps(interseccion, sensor_id):
    evento = {
        "sensor_id": sensor_id,
        "tipo_sensor": "gps",
        "interseccion": interseccion,
        "nivel_congestion": random.choice(NIVELES_CONGESTION),
        "velocidad_promedio": round(random.uniform(5, 60), 1),
        "timestamp": _ts(),
    }
    return f"gps {json.dumps(evento)}"


def _msg_espira(interseccion, sensor_id):
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


class GeneradorControlable:
    def __init__(self, broker_ip, puerto_control):
        self.broker_ip = broker_ip
        self.puerto_control = puerto_control
        self.intersecciones = INTERSECCIONES_GRILLA

        # Estado de generación
        self.generando = False
        self.tasa_actual = 0
        self.duracion_actual = 0
        self.enviados_ultima_ronda = 0
        self.lock = threading.Lock()
        self.stop_event = threading.Event()

        # ZMQ
        self.ctx = zmq.Context()

        # Socket PUB para enviar al broker
        self.pub_socket = self.ctx.socket(zmq.PUB)
        self.pub_socket.setsockopt(zmq.SNDHWM, 50000)
        self.pub_socket.connect(f"tcp://{broker_ip}:5555")

        # Socket REP para recibir comandos de PC2
        self.rep_socket = self.ctx.socket(zmq.REP)
        self.rep_socket.bind(f"tcp://*:{puerto_control}")

        print(f"[GEN-ESTRES] Conectado al broker en tcp://{broker_ip}:5555")
        print(f"[GEN-ESTRES] Escuchando comandos en tcp://*:{puerto_control}")

        # Pausa para slow joiner
        time.sleep(0.5)

    def _generar(self, tasa, duracion):
        """Genera mensajes a la tasa indicada durante duracion segundos."""
        intervalo = 1.0 / tasa if tasa > 0 else 1.0
        t_inicio = time.monotonic()
        t_fin = t_inicio + duracion
        enviados = 0
        idx_tipo = 0
        idx_int = 0
        n_tipos = len(_GENERADORES)
        n_ints = len(self.intersecciones)
        t_sig = time.monotonic()
        t_reporte = t_inicio

        print(f"[GEN-ESTRES] Generando: tasa={tasa} msg/s | duracion={duracion}s")

        while not self.stop_event.is_set():
            ahora = time.monotonic()
            if ahora >= t_fin:
                break

            if t_sig > ahora:
                wait = min(t_sig - ahora, 0.01)
                time.sleep(wait)
                continue

            t_sig += intervalo

            interseccion = self.intersecciones[idx_int % n_ints]
            tipo_idx = idx_tipo % n_tipos
            sensor_id = f"GEN-{interseccion}-{('CAM', 'GPS', 'ESP')[tipo_idx]}"
            mensaje = _GENERADORES[tipo_idx](interseccion, sensor_id)

            try:
                self.pub_socket.send_string(mensaje, zmq.NOBLOCK)
                enviados += 1
            except zmq.Again:
                pass

            idx_tipo += 1
            idx_int += 1

            # Reporte cada 10s
            ahora = time.monotonic()
            if ahora - t_reporte >= 10.0:
                elapsed = ahora - t_reporte
                tasa_real = enviados / (ahora - t_inicio) if ahora > t_inicio else 0
                restante = max(0, t_fin - ahora)
                print(f"[GEN-ESTRES] Tasa real: {tasa_real:.0f} msg/s | "
                      f"Enviados: {enviados} | Restante: {restante:.0f}s")
                t_reporte = ahora

        with self.lock:
            self.enviados_ultima_ronda = enviados
            self.generando = False

        print(f"[GEN-ESTRES] Ronda terminada. Enviados: {enviados}")

    def _hilo_generador(self, tasa, duracion):
        """Wrapper para correr _generar en un hilo separado."""
        self._generar(tasa, duracion)

    def procesar_comando(self, cmd: dict) -> dict:
        """Procesa un comando recibido de PC2."""
        accion = cmd.get("accion", "")

        if accion == "iniciar":
            tasa = cmd.get("tasa", 1000)
            duracion = cmd.get("duracion", 60)

            # Si ya está generando, parar primero
            if self.generando:
                self.stop_event.set()
                time.sleep(1)

            self.stop_event.clear()
            with self.lock:
                self.generando = True
                self.tasa_actual = tasa
                self.duracion_actual = duracion
                self.enviados_ultima_ronda = 0

            t = threading.Thread(target=self._hilo_generador, args=(tasa, duracion),
                                 daemon=True)
            t.start()
            return {"status": "ok", "tasa": tasa, "duracion": duracion}

        elif accion == "parar":
            self.stop_event.set()
            time.sleep(0.5)
            with self.lock:
                self.generando = False
            return {"status": "ok", "msg": "generador detenido"}

        elif accion == "stats":
            with self.lock:
                return {
                    "status": "ok",
                    "generando": self.generando,
                    "tasa_actual": self.tasa_actual,
                    "enviados_ultima_ronda": self.enviados_ultima_ronda,
                }

        else:
            return {"status": "error", "msg": f"accion desconocida: {accion}"}

    def run(self):
        """Loop principal: escucha comandos por REP."""
        print(f"[GEN-ESTRES] Listo. Esperando comandos...")
        try:
            while True:
                msg = self.rep_socket.recv_string()
                try:
                    cmd = json.loads(msg)
                except json.JSONDecodeError:
                    self.rep_socket.send_string(json.dumps(
                        {"status": "error", "msg": "JSON inválido"}))
                    continue

                resp = self.procesar_comando(cmd)
                self.rep_socket.send_string(json.dumps(resp))
        except KeyboardInterrupt:
            print("\n[GEN-ESTRES] Detenido por el usuario")
        finally:
            self.stop_event.set()
            self.pub_socket.close()
            self.rep_socket.close()
            self.ctx.term()


def main():
    parser = argparse.ArgumentParser(description="Generador controlable para prueba de estrés GITU")
    parser.add_argument("--broker-ip", default="127.0.0.1",
                        help="IP del broker (default: 127.0.0.1)")
    parser.add_argument("--puerto-control", type=int, default=6010,
                        help="Puerto para recibir comandos de PC2 (default: 6010)")
    args = parser.parse_args()

    gen = GeneradorControlable(args.broker_ip, args.puerto_control)
    gen.run()


if __name__ == "__main__":
    main()
