import zmq
import sqlite3
import json


class BaseDatos():
    DB = "bd_replica.db"

    def conectar(self):
        return sqlite3.connect(self.DB)

    def tabla_GPS(self):
        with self.conectar() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS GPS(
                    ID TEXT PRIMARY KEY,
                    TIPO_SENSOR TEXT,
                    INTERSECCION TEXT,
                    NIVEL_CONGESTION TEXT,
                    VELOCIDAD_PROMEDIO REAL,
                    TIMESTAMP TEXT
                )
            """)  

    def tabla_Camara(self):
        with self.conectar() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS CAMARA(
                    ID TEXT PRIMARY KEY,
                    TIPO_SENSOR TEXT,
                    INTERSECCION TEXT,
                    VOLUMEN INTEGER,
                    VELOCIDAD_PROMEDIO REAL,
                    COLA_HORIZONTAL INTEGER,
                    COLA_VERTICAL INTEGER,
                    TIMESTAMP TEXT
                )
            """)  

    def tabla_Espira(self):
        with self.conectar() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS ESPIRA(
                    ID TEXT PRIMARY KEY,
                    TIPO_SENSOR TEXT,
                    INTERSECCION TEXT,
                    VEHICULOS_CONTADOS INTEGER,
                    INTERVALO_SEGUNDOS INTEGER,
                    TIMESTAMP_INICIO TEXT,
                    TIMESTAMP_FIN TEXT
                )
            """)  

    def tabla_Decisiones(self):
        """Tabla para almacenar las decisiones del servicio de analítica."""
        with self.conectar() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS DECISIONES(
                    ID INTEGER PRIMARY KEY AUTOINCREMENT,
                    INTERSECCION TEXT,
                    ESTADO_TRAFICO TEXT,
                    ACCION TEXT,
                    TIMESTAMP TEXT
                )
            """)

    def insertar_GPS(self, id, tipo, inter, congestion, velocidad, timestamp):
        with self.conectar() as con:
            con.execute("""
                INSERT INTO GPS (ID, TIPO_SENSOR, INTERSECCION, NIVEL_CONGESTION, VELOCIDAD_PROMEDIO, TIMESTAMP)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (f"{id}_{timestamp}", tipo, inter, congestion, velocidad, timestamp))

    def insertar_Camara(self, id, tipo, inter, volumen, velocidad, cola_h, cola_v, timestamp):
        with self.conectar() as con:
            con.execute("""
                INSERT INTO CAMARA (ID, TIPO_SENSOR, INTERSECCION, VOLUMEN, VELOCIDAD_PROMEDIO, COLA_HORIZONTAL, COLA_VERTICAL, TIMESTAMP)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (f"{id}_{timestamp}", tipo, inter, volumen, velocidad, cola_h, cola_v, timestamp))

    def insertar_Espira(self, id, tipo, inter, vehiculos, intervalo, ts_inicio, ts_fin):
        with self.conectar() as con:
            con.execute("""
                INSERT INTO ESPIRA (ID, TIPO_SENSOR, INTERSECCION, VEHICULOS_CONTADOS, INTERVALO_SEGUNDOS, TIMESTAMP_INICIO, TIMESTAMP_FIN)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (f"{id}_{ts_inicio}", tipo, inter, vehiculos, intervalo, ts_inicio, ts_fin))

    def insertar_Decision(self, interseccion, estado_trafico, accion, timestamp):
        with self.conectar() as con:
            con.execute("""
                INSERT INTO DECISIONES (INTERSECCION, ESTADO_TRAFICO, ACCION, TIMESTAMP)
                VALUES (?, ?, ?, ?)
            """, (interseccion, estado_trafico, accion, timestamp))

    def __init__(self):
        self.context = zmq.Context()
        self.pull_socket = self.context.socket(zmq.PULL)
        self.pull_socket.bind("tcp://*:7002")
        self.tabla_GPS()     
        self.tabla_Camara()
        self.tabla_Espira()
        self.tabla_Decisiones()

    def run(self):
        print("[BD REPLICA] Iniciada. Escuchando en :7002")
        while True:
            mensaje = self.pull_socket.recv_string()
            dato = json.loads(mensaje)
            evento = dato["evento"]
            estado_trafico = dato.get("estado_trafico", "DESCONOCIDO")
            accion = dato.get("accion", "SIN_ACCION")
            timestamp_decision = dato.get("timestamp", "")

            print(f"💾 [BD REPLICA] Recibido: {evento['tipo_sensor']} | {evento['interseccion']} | estado: {estado_trafico} | accion: {accion}")

            if evento["tipo_sensor"] == "gps":
                self.insertar_GPS(
                    evento["sensor_id"],
                    evento["tipo_sensor"],
                    evento["interseccion"],
                    evento["nivel_congestion"],
                    evento["velocidad_promedio"],
                    evento["timestamp"]
                )
            elif evento["tipo_sensor"] == "camara":
                self.insertar_Camara(
                    evento["sensor_id"],
                    evento["tipo_sensor"],
                    evento["interseccion"],
                    evento["volumen"],
                    evento["velocidad_promedio"],
                    evento["cola_horizontal"],
                    evento["cola_vertical"],
                    evento["timestamp"]
                )
            elif evento["tipo_sensor"] == "espira_inductiva":
                self.insertar_Espira(
                    evento["sensor_id"],
                    evento["tipo_sensor"],
                    evento["interseccion"],
                    evento["vehiculos_contados"],
                    evento["intervalo_segundos"],
                    evento["timestamp_inicio"],
                    evento["timestamp_fin"]
                )

            # Siempre registrar la decisión de la analítica
            self.insertar_Decision(
                dato.get("interseccion", evento["interseccion"]),
                estado_trafico,
                accion,
                timestamp_decision
            )

if __name__ == "__main__":
    BD = BaseDatos()
    BD.run()
