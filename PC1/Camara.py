from Sensores import Sensores

class Camara(Sensores):
    def __init__ (self,Sensor_id, Tipo_sensor, Interseccion, Timespant, Broker_puerto,Volumen,Velocidad_promedio):

        super().__init__(Sensor_id, Tipo_sensor, Interseccion, Timespant, Broker_puerto)

        self.Volumen = Volumen
        self.Velocidad_promedio = Velocidad_promedio

    def Asignar_Tipo_sensor(self):
        self.Tipo_sensor = "Camara"

    def Generar_id(self,M,N,i):
        self.Sensor_id = f"CAM{i} C{M}{N}"
