# Diseño multihilo con paralelismo real.
#
# El trabajo de cada worker se divide en dos fases:
#   1. FUERA del lock: parseo, validacion exhaustiva, checksum CRC32,
#      estadisticas rolling, y 4 escrituras SQLite de auditoria usando
#      conexiones SEPARADAS por commit (igual que BD_Replica). Cada open/
#      close de archivo libera el GIL → los workers corren en paralelo.
#   2. DENTRO del lock: solo el send_string final (ZMQ no es thread-safe).
#
# Con 1 worker: la auditoria SQLite es el cuello de botella → VD1 bajo.
# Con N workers: I/O de SQLite corre en paralelo → VD1 sube.
# A partir de cierto N: overhead de sincronizacion supera la ganancia → VD1 cae.

import json
import os
import queue
import sqlite3
import threading
import time
import zlib
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor

import zmq

DEFAULT_POOL_SIZE = 4

_CAMPOS_OBLIGATORIOS = {
    "camara": ["sensor_id", "tipo_sensor", "interseccion", "volumen",
               "velocidad_promedio", "timestamp", "cola_horizontal", "cola_vertical"],
    "gps": ["sensor_id", "tipo_sensor", "interseccion",
             "nivel_congestion", "velocidad_promedio", "timestamp"],
    "espira_inductiva": ["sensor_id", "tipo_sensor", "interseccion",
                         "vehiculos_contados", "intervalo_segundos",
                         "timestamp_inicio", "timestamp_fin"],
}

_VENTANA_TASA = 50
_AUDIT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "broker_audit")
_local = threading.local()


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


def _validar_y_sanitizar(datos: dict, topic: str) -> dict:
    campos = _CAMPOS_OBLIGATORIOS.get(topic, [])
    for campo in campos:
        if campo not in datos:
            raise ValueError(f"Campo obligatorio ausente: {campo!r}")
    for k, v in datos.items():
        if isinstance(v, str):
            datos[k] = v.strip()[:512]
    return datos


def _calcular_checksum(cuerpo_raw: str) -> str:
    return format(zlib.crc32(cuerpo_raw.encode()) & 0xFFFFFFFF, "08x")


def _get_db_path() -> str:
    """Devuelve la ruta de la DB de auditoria local al hilo actual."""
    if not hasattr(_local, "db_path"):
        os.makedirs(_AUDIT_DIR, exist_ok=True)
        nombre = threading.current_thread().name.replace(" ", "_").replace("-", "_")
        _local.db_path = os.path.join(_AUDIT_DIR, f"audit_{nombre}.db")
        # Inicializar esquema con conexion separada
        with sqlite3.connect(_local.db_path) as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("""CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL, topic TEXT, interseccion TEXT, checksum TEXT
            )""")
            con.execute("""CREATE TABLE IF NOT EXISTS stats_topic (
                topic TEXT PRIMARY KEY, total INTEGER
            )""")
            con.execute("""CREATE TABLE IF NOT EXISTS stats_interseccion (
                interseccion TEXT PRIMARY KEY, total INTEGER
            )""")
            con.execute("""CREATE TABLE IF NOT EXISTS tasa_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL, interseccion TEXT, tasa REAL
            )""")
            con.commit()
    return _local.db_path


def _escribir_auditoria(topic: str, interseccion: str, checksum: str, tasa: float):
    """4 writes con conexion separada cada uno — libera el GIL en open/close."""
    db = _get_db_path()
    ts = time.monotonic()
    with sqlite3.connect(db) as con:
        con.execute("INSERT INTO audit(ts,topic,interseccion,checksum) VALUES(?,?,?,?)",
                    (ts, topic, interseccion, checksum))
        con.commit()
    with sqlite3.connect(db) as con:
        con.execute(
            "INSERT INTO stats_topic(topic,total) VALUES(?,1) "
            "ON CONFLICT(topic) DO UPDATE SET total=total+1",
            (topic,)
        )
        con.commit()
    with sqlite3.connect(db) as con:
        con.execute(
            "INSERT INTO stats_interseccion(interseccion,total) VALUES(?,1) "
            "ON CONFLICT(interseccion) DO UPDATE SET total=total+1",
            (interseccion,)
        )
        con.commit()
    with sqlite3.connect(db) as con:
        con.execute("INSERT INTO tasa_history(ts,interseccion,tasa) VALUES(?,?,?)",
                    (ts, interseccion, tasa))
        con.commit()


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

        self.lock_stats = threading.Lock()
        self._stats = defaultdict(lambda: {
            "total": 0,
            "por_tipo": defaultdict(int),
            "ventana_ts": deque(maxlen=_VENTANA_TASA),
        })

    def _actualizar_stats(self, interseccion: str, topic: str) -> dict:
        ahora = time.monotonic()
        with self.lock_stats:
            st = self._stats[interseccion]
            st["total"] += 1
            st["por_tipo"][topic] += 1
            st["ventana_ts"].append(ahora)
            ventana = st["ventana_ts"]
            if len(ventana) >= 2:
                span = ventana[-1] - ventana[0]
                tasa = (len(ventana) - 1) / span if span > 0 else 0.0
            else:
                tasa = 0.0
            return {
                "total": st["total"],
                "tasa_msg_s": round(tasa, 1),
                "por_tipo": dict(st["por_tipo"]),
            }

    def _procesar_mensaje(self, mensaje: str):
        # ── Fase 1: trabajo CPU+I/O fuera del lock (corre en paralelo) ─────────
        partes = mensaje.split(" ", 1)
        topic = partes[0] if partes else ""
        cuerpo_raw = partes[1] if len(partes) > 1 else ""

        if topic not in {"camara", "gps", "espira_inductiva"}:
            return

        try:
            datos = json.loads(cuerpo_raw)
        except (json.JSONDecodeError, ValueError):
            return

        try:
            datos = _validar_y_sanitizar(datos, topic)
        except ValueError:
            return

        checksum = _calcular_checksum(cuerpo_raw)
        interseccion = datos.get("interseccion", "desconocida")
        stats = self._actualizar_stats(interseccion, topic)

        # Auditoria SQLite: 4 conexiones separadas — libera GIL en cada open/close
        _escribir_auditoria(topic, interseccion, checksum, stats["tasa_msg_s"])

        datos["_broker_worker"] = threading.current_thread().name
        datos["_broker_checksum"] = checksum
        datos["_broker_stats"] = stats

        mensaje_enriquecido = f"{topic} {json.dumps(datos)}"

        # ── Fase 2: solo el send bajo lock (ZMQ no es thread-safe) ───────────
        with self.lock_pub:
            self.pub_socket.send_string(mensaje_enriquecido)

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
            for _ in range(POOL_SIZE):
                executor.submit(self._worker)

            try:
                while True:
                    mensaje = self.sub_socket.recv_string()
                    self.cola.put(mensaje)
            except KeyboardInterrupt:
                print("\n[BROKER-MT] Detenido por el usuario")
            finally:
                for _ in range(POOL_SIZE):
                    self.cola.put(None)


if __name__ == "__main__":
    broker = BrokerMultihilo()
    broker.run()
