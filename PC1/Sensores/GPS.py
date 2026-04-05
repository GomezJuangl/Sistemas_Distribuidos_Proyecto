from Sensores.Sensores import Sensores
import json

class GPS(Sensores):
    def __init__(self, Sensor_id, Interseccion, Timespant, socket, Velocidad_promedio, Nivel_congestion):
        super().__init__(Sensor_id, "GPS", Interseccion, Timespant, socket)
        self.Velocidad_promedio = Velocidad_promedio
        self.Nivel_congestion = Nivel_congestion

    def Generar_id(self, M, N):
        self.set_Sensor_id(f"GPS-{M}{N}")

    def Envio_de_datos(self):
        evento = {
            "sensor_id": self.Sensor_id,
            "tipo_sensor": "gps",
            "interseccion": f"INT_{self.Interseccion[0]}{self.Interseccion[1]}",
            "nivel_congestion": self.Nivel_congestion,
            "velocidad_promedio": self.Velocidad_promedio,
            "timestamp": self.Calcular_Timestamp(),
        }
        mensaje = json.dumps(evento)
        print(f"🛰️  [ENVÍO] {self.Sensor_id}: {mensaje}")
        self.socket.send_string(f"gps {mensaje}")