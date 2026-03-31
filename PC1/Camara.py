from Sensores import Sensores
import json

class Camara(Sensores):
    def __init__(self, Sensor_id, Interseccion, Timespant, socket, Volumen, Velocidad_promedio):
        super().__init__(Sensor_id, "Camara", Interseccion, Timespant, socket)
        self.Volumen = Volumen
        self.Velocidad_promedio = Velocidad_promedio

    def Generar_id(self, M, N):
        self.set_Sensor_id(f"CAM-{M}{N}")

    def Envio_de_datos(self):
        evento = {
            "sensor_id": self.Sensor_id,
            "tipo_sensor": "camara",
            "interseccion": f"INT-{self.Interseccion[0]}{self.Interseccion[1]}",
            "volumen": self.Volumen,
            "velocidad_promedio": self.Velocidad_promedio,
            "timestamp": self.Calcular_Timestamp()
        }
        print(f"📹 [ENVÍO] {self.Sensor_id}: {json.dumps(evento)}")
        self.socket.send_string(json.dumps(evento))