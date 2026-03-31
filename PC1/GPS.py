from Sensores import Sensores

class GPS(Sensores):
    def __init__(self, Sensor_id, Interseccion, Timespant, Broker_puerto, Nivel_congestion, Velocidad_promedio):
        super().__init__(Sensor_id, None, Interseccion, Timespant, Broker_puerto)
        self.Nivel_congestion = Nivel_congestion
        self.Velocidad_promedio = Velocidad_promedio
        self.set_Tipo_sensor("GPS")

    def Generar_id(self, M, N):
        self.set_Sensor_id(f"GPS-G{M}{N}")