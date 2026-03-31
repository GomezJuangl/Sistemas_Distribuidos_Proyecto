from Sensores import Sensores

class GPS(Sensores):
    def __init__(self, Sensor_id, Interseccion, Timespant, socket, Nivel_congestion, Velocidad_promedio):
        super().__init__(Sensor_id, "GPS", Interseccion, Timespant, socket)
        self.Nivel_congestion = Nivel_congestion
        self.Velocidad_promedio = Velocidad_promedio

    def Generar_id(self, M, N):
        self.set_Sensor_id(f"GPS-{M}{N}")
