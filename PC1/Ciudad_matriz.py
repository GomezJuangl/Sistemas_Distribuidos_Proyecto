from Interseccion import Interseccion

class Ciudad_matriz:
    def __init__(self, ancho, largo):
        self.Ancho = ancho
        self.Largo = largo
        self.Matriz = []
        self.construir_matriz()

    def construir_matriz(self):
        filas = ["A", "B", "C", "D"]
        for a in filas:
            fila = []
            for b in range(1, self.Largo + 1):
                interseccion = Interseccion(a, b)
                fila.append(interseccion)
            self.Matriz.append(fila)

    def Mostrar_matriz(self):
        for fila in self.Matriz:
            for interseccion in fila:
                interseccion.Mostrar_IDS()
                print("----------")