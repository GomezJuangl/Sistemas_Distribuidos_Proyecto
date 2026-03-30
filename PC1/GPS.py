from Sensores import Sensores

class GPS(Sensores):

    def __init__(self, Sensor_id, Tipo_sensor, Interseccion, Timespant, Broker_puerto, Nivel_congestion, Velocidad_promedio):
        
        super().__init__(Sensor_id, Tipo_sensor, Interseccion, Timespant, Broker_puerto)
        
        self.Nivel_congestion = Nivel_congestion
        self.Velocidad_promedio = Velocidad_promedio
        self.set_Tipo_sensor("GPS")
    
    def Generar_id(self,Interseccion,i):
        self.Sensor_id = f"GPS{i} G{Interseccion}"

