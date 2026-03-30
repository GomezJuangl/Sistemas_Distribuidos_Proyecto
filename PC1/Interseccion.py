from GPS import GPS
from Camara import Camara
from Espira_inductiva import Espira_inductiva

class Interseccion():
    def __init__(self,M,N,camara,gps,espira_inductiva):
        self.M = M
        self.N = N
        self.Camara = camara
        self.GPS = gps
        self.Espira_inductiva = espira_inductiva

    def set_M(self, new_M):
        self.M = new_M
    
    def set_N(self, new_N):
        self.N = new_N
    
    def Mostrar_IDS(self):
        print(f"Camara: {self.Camara.get_Sensor_id()}")
        print(f"GPS: {self.GPS.get_Sensor_id()}")
        print(f"Espira_inductiva: {self.Espira_inductiva.get_Sensor_id()}")

