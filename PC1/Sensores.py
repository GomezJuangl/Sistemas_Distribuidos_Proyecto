class Sensores():
    
    def __init__(self, Sensor_id, Tipo_sensor, Interseccion, Timespant, Broker_puerto):

        self.Sensor_id=Sensor_id
        self.Tipo_sensor=Tipo_sensor
        self.Interseccion=Interseccion
        self.Timespant=Timespant
        self.Broker_puerto=Broker_puerto

    def set_Sensor_id(self,new_id):
        self.Sensor_id = new_id
        
    def get_Sensor_id(self):
        return self.Sensor_id
    
    def set_Tipo_sensor(self,new_tipo):
        self.Tipo_sensor = new_tipo

    def set_Interseccion(self,M,N):
        self.Interseccion = [M,N]

    def Calcular_Timestamp(self):
        pass

    def Envio_de_datos(self):
        pass