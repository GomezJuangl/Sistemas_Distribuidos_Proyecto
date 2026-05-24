import json
import os
import sqlite3
import time
import zlib
from collections import defaultdict, deque
import zmq

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
_AUDIT_DB = os.path.join(_AUDIT_DIR, "audit_broker_main.db")


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


def _init_audit_db(db_path: str):
    with sqlite3.connect(db_path) as con:
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


def _escribir_auditoria(topic: str, interseccion: str, checksum: str, tasa: float):
    """4 writes con conexion separada — mismo costo que 1 worker en Broker_multihilo."""
    ts = time.monotonic()
    with sqlite3.connect(_AUDIT_DB) as con:
        con.execute("INSERT INTO audit(ts,topic,interseccion,checksum) VALUES(?,?,?,?)",
                    (ts, topic, interseccion, checksum))
        con.commit()
    with sqlite3.connect(_AUDIT_DB) as con:
        con.execute(
            "INSERT INTO stats_topic(topic,total) VALUES(?,1) "
            "ON CONFLICT(topic) DO UPDATE SET total=total+1",
            (topic,)
        )
        con.commit()
    with sqlite3.connect(_AUDIT_DB) as con:
        con.execute(
            "INSERT INTO stats_interseccion(interseccion,total) VALUES(?,1) "
            "ON CONFLICT(interseccion) DO UPDATE SET total=total+1",
            (interseccion,)
        )
        con.commit()
    with sqlite3.connect(_AUDIT_DB) as con:
        con.execute("INSERT INTO tasa_history(ts,interseccion,tasa) VALUES(?,?,?)",
                    (ts, interseccion, tasa))
        con.commit()


class Broker:
    def __init__(self):
        self.context = zmq.Context()

        self.sub_socket = self.context.socket(zmq.SUB)
        self.sub_socket.bind("tcp://*:5555")
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "camara")
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "gps")
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "espira_inductiva")

        self.pub_socket = self.context.socket(zmq.PUB)
        self.pub_socket.bind("tcp://*:5556")

        self._stats = defaultdict(lambda: {
            "total": 0,
            "por_tipo": defaultdict(int),
            "ventana_ts": deque(maxlen=_VENTANA_TASA),
        })

        os.makedirs(_AUDIT_DIR, exist_ok=True)
        _init_audit_db(_AUDIT_DB)

    def _actualizar_stats(self, interseccion: str, topic: str) -> dict:
        ahora = time.monotonic()
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

    def _procesar_mensaje(self, mensaje: str) -> str | None:
        partes = mensaje.split(" ", 1)
        topic = partes[0] if partes else ""
        cuerpo_raw = partes[1] if len(partes) > 1 else ""

        if topic not in {"camara", "gps", "espira_inductiva"}:
            return None

        try:
            datos = json.loads(cuerpo_raw)
        except (json.JSONDecodeError, ValueError):
            return None

        try:
            datos = _validar_y_sanitizar(datos, topic)
        except ValueError:
            return None

        checksum = _calcular_checksum(cuerpo_raw)
        interseccion = datos.get("interseccion", "desconocida")
        stats = self._actualizar_stats(interseccion, topic)

        _escribir_auditoria(topic, interseccion, checksum, stats["tasa_msg_s"])

        datos["_broker_checksum"] = checksum
        datos["_broker_stats"] = stats

        return f"{topic} {json.dumps(datos)}"

    def run(self):
        print("[BROKER] Iniciado. Escuchando en :5555, reenviando en :5556")
        print("[BROKER] Suscrito a tópicos: camara, gps, espira_inductiva")
        try:
            while True:
                mensaje = self.sub_socket.recv_string()
                enriquecido = self._procesar_mensaje(mensaje)
                if enriquecido:
                    self.pub_socket.send_string(enriquecido)
        except KeyboardInterrupt:
            print("\n[BROKER] Detenido por el usuario")
        finally:
            self.sub_socket.close()
            self.pub_socket.close()
            self.context.term()


if __name__ == "__main__":
    broker = Broker()
    broker.run()
