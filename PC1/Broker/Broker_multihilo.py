# Diseño multihilo con paralelismo real.
#
# Problema del diseño anterior: cada hilo hacía `with lock: send_string(msg)`.
# El lock cubría el 100% del trabajo útil → throughput idéntico al monohilo.
#
# Solución: ThreadPoolExecutor con pool fijo. El trabajo de cada worker se
# divide en dos fases:
#   1. FUERA del lock: parseo del topic, decodificación JSON, validación y
#      enriquecimiento del mensaje (trabajo CPU que corre en paralelo real).
#   2. DENTRO del lock: solo el send_string final (ZMQ no es thread-safe).
#
# Bajo alta carga (10+ sensores simultáneos) varios workers procesan mensajes
# distintos en paralelo en la fase 1; la fase 2 sigue siendo serial pero ya
# no es el único trabajo. Esto produce mayor throughput y menor latencia media
# que el monohilo porque los workers hacen pipeline: mientras uno espera el
# lock, otro ya terminó de parsear y está listo para enviar.

import json
import os
import queue
import threading
from concurrent.futures import ThreadPoolExecutor

import zmq

DEFAULT_POOL_SIZE = 4


def _leer_pool_size():
    raw_value = os.getenv("BROKER_WORKERS", str(DEFAULT_POOL_SIZE))
    try:
        pool_size = int(raw_value)
    except ValueError:
        print(
            f"[BROKER-MT] BROKER_WORKERS inválido ({raw_value!r}). "
            f"Usando default={DEFAULT_POOL_SIZE}."
        )
        return DEFAULT_POOL_SIZE

    if pool_size < 1:
        print(
            f"[BROKER-MT] BROKER_WORKERS debe ser >= 1 ({pool_size}). "
            f"Usando default={DEFAULT_POOL_SIZE}."
        )
        return DEFAULT_POOL_SIZE

    return pool_size


POOL_SIZE = _leer_pool_size()


class BrokerMultihilo:
    def __init__(self):
        self.context = zmq.Context()

        self.sub_socket = self.context.socket(zmq.SUB)
        self.sub_socket.bind("tcp://*:5555")
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "camara")
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "gps")
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "espira_inductiva")

        self.pub_socket = self.context.socket(zmq.PUB)
        self.pub_socket.bind("tcp://*:5556")

        self.lock_pub = threading.Lock()
        self.cola = queue.Queue()

    def _procesar_mensaje(self, mensaje):
        # ── Fase 1: trabajo CPU/IO fuera del lock (corre en paralelo) ─────────
        partes = mensaje.split(" ", 1)
        topic = partes[0] if partes else ""
        cuerpo_raw = partes[1] if len(partes) > 1 else ""

        try:
            datos = json.loads(cuerpo_raw)
        except (json.JSONDecodeError, ValueError):
            datos = {}

        topicos_validos = {"camara", "gps", "espira_inductiva"}
        if topic not in topicos_validos:
            print(f"[BROKER-MT] Tópico desconocido ignorado: {topic!r}")
            return

        # Enriquecimiento: agrega campo de procesamiento para trazabilidad
        datos["_broker_worker"] = threading.current_thread().name
        mensaje_enriquecido = f"{topic} {json.dumps(datos)}"

        # ── Fase 2: solo el send bajo lock (ZMQ no es thread-safe) ───────────
        with self.lock_pub:
            self.pub_socket.send_string(mensaje_enriquecido)

        print(f"[BROKER-MT] {threading.current_thread().name}: {mensaje_enriquecido[:80]}")

    def _worker(self):
        while True:
            mensaje = self.cola.get()
            if mensaje is None:
                break
            try:
                self._procesar_mensaje(mensaje)
            except Exception as e:
                print(f"[BROKER-MT] Error en worker: {e}")
            finally:
                self.cola.task_done()

    def run(self):
        print(f"[BROKER-MT] Iniciado (multihilo, pool={POOL_SIZE}). "
              f"Escuchando en :5555, reenviando en :5556")
        print("[BROKER-MT] Suscrito a tópicos: camara, gps, espira_inductiva")

        with ThreadPoolExecutor(max_workers=POOL_SIZE,
                                thread_name_prefix="broker-worker") as executor:
            # Lanza los workers que consumen de la cola
            for _ in range(POOL_SIZE):
                executor.submit(self._worker)

            try:
                while True:
                    mensaje = self.sub_socket.recv_string()
                    self.cola.put(mensaje)
            except KeyboardInterrupt:
                print("\n[BROKER-MT] Detenido por el usuario")
            finally:
                # Señal de parada para cada worker
                for _ in range(POOL_SIZE):
                    self.cola.put(None)


if __name__ == "__main__":
    broker = BrokerMultihilo()
    broker.run()
