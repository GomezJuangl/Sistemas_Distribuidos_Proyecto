import zmq
import sqlite3
import json

class BaseDatos():
    DB = "bd_principal.db" 

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

    def insertar_GPS(self,id,tipo,inter,congestion,velocidad,timestamp):
        with self.conectar() as con:
            con.execute("""
                INSERT INTO GPS (ID,TIPO_SENSOR,INTERSECCION,NIVEL_CONGESTION,VELOCIDAD_PROMEDIO,TIMESTAMP)
                VALUES(?,?,?,?,?,?)
            """,(id,tipo,inter,congestion,velocidad,timestamp))

    def insertar_Camara(self, id, tipo, inter, volumen, velocidad, cola_h, cola_v, timestamp):
        with self.conectar() as con:
            con.execute("""
                INSERT INTO CAMARA (ID, TIPO_SENSOR, INTERSECCION, VOLUMEN, VELOCIDAD_PROMEDIO, COLA_HORIZONTAL, COLA_VERTICAL, TIMESTAMP)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (id, tipo, inter, volumen, velocidad, cola_h, cola_v, timestamp))

    def insertar_Espira(self, id, tipo, inter, vehiculos, intervalo, ts_inicio, ts_fin):
        with self.conectar() as con:
            con.execute("""
                INSERT INTO ESPIRA (ID, TIPO_SENSOR, INTERSECCION, VEHICULOS_CONTADOS, INTERVALO_SEGUNDOS, TIMESTAMP_INICIO, TIMESTAMP_FIN)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (id, tipo, inter, vehiculos, intervalo, ts_inicio, ts_fin))


    def __init__(self):
        self.context = zmq.Context()
        self.pull_socket = self.context.socket(zmq.PULL)
        self.pull_socket.connect("tcp://localhost:6000")
        self.tabla_GPS()      # crear tablas al iniciar
        self.tabla_Camara()
        self.tabla_Espira()

    def run(self):
        while True:
            mensaje = self.pull_socket.recv_string()
            dato = json.loads(mensaje)

            if dato["tipo_sensor"] == "gps":
                self.insertar_GPS(
                    dato["sensor_id"],
                    dato["tipo_sensor"],
                    dato["interseccion"],
                    dato["nivel_congestion"],
                    dato["velocidad_promedio"],
                    dato["timestamp"]
                )
            print("Recibido", mensaje)

if __name__ == "__main__":
    BD = BaseDatos()
    BD.run()