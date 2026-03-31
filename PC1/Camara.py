from Sensores import Sensores

class Camara(Sensores):
    def __init__(self, Sensor_id, Interseccion, Timespant, socket, Volumen, Velocidad_promedio):
        super().__init__(Sensor_id, "Camara", Interseccion, Timespant, socket)
        self.Volumen = Volumen
        self.Velocidad_promedio = Velocidad_promedio

    def Generar_id(self, M, N):
        self.set_Sensor_id(f"CAM-{M}{N}")
