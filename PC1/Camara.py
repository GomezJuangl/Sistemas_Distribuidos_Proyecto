from Sensores import Sensores

class Camara(Sensores):
    def __init__(self, Sensor_id, Interseccion, Timespant, Broker_puerto, Volumen, Velocidad_promedio):
        super().__init__(Sensor_id, None, Interseccion, Timespant, Broker_puerto)
        self.Volumen = Volumen
        self.Velocidad_promedio = Velocidad_promedio
        self.set_Tipo_sensor("Camara")

    def Generar_id(self, M, N):
        self.set_Sensor_id(f"CAM-C{M}{N}")
