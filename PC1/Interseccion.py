from GPS import GPS
from Camara import Camara
from Espira_inductiva import Espira_inductiva

class Interseccion:
    def __init__(self, M, N, socket):
        self.M = M
        self.N = N
        self.Interseccion = [M, N]
        self.Camara = Camara("", [M, N], 30, socket, 0, 0)
        self.GPS = GPS("", [M, N], 30, socket, 0, 0)
        self.Espira_inductiva = Espira_inductiva("", [M, N], 30, socket, 0, 30, None, None)
        self.Camara.Generar_id(self.M, self.N)
        self.GPS.Generar_id(self.M, self.N)
        self.Espira_inductiva.Generar_id(self.M, self.N)

    def set_M(self, new_M):
        self.M = new_M

    def set_N(self, new_N):
        self.N = new_N

    def Mostrar_IDS(self):
        print(f"Camara:           {self.Camara.get_Sensor_id()}")
        print(f"GPS:              {self.GPS.get_Sensor_id()}")
        print(f"Espira_inductiva: {self.Espira_inductiva.get_Sensor_id()}")