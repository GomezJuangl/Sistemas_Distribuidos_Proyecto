import zmq
import json

class Monitoreo_Consulta():
    def __init__(self):
        self.IP = ""
        self.Puerto_BDP = 5101 
        self.context = zmq.Context()
        self.req_socket = self.context.socket(zmq.REQ)
        self.req_socket.connect(f"tcp://localhost:{self.Puerto_BDP}")

        self.Puerto_Analitica = 6001
        self.req_analitica = self.context.socket(zmq.REQ)
        self.req_analitica.connect(f"tcp://localhost:{self.Puerto_Analitica}")

        self.usuario = None



    def ConsultaBD(self):
        print("\n" + "=" * 50)
        print("  SERVICIO DE MONITOREO Y CONSULTA")
        print("=" * 50)
        print("1. Consultar estado actual de una intersección")
        print("2. Consultar histórico entre dos fechas")
        print("3. Ver decisiones de congestión en una intersección")
        print("4. Forzar ola verde (ambulancia)")
        print("5. Salir")
        print("=" * 50)

        opcion = input("Seleccione una opción: ")

        if opcion == "1":
            interseccion = input("Ingrese la intersección (ej: INT_B3): ").upper()
            if not interseccion.startswith("INT_"):
                print("Formato inválido. Use INT_LetraNumero (ej: INT_B3)")
                return True
            consulta = json.dumps({
                "tipo": "estado_actual",
                "interseccion": interseccion
            })
            self.req_socket.send_string(consulta)
            respuesta = self.req_socket.recv_string()
            print(respuesta)

        elif opcion == "2":
            print("Formato de fecha: 2026-04-02T19:00:00")
            inicio = input("Fecha inicio: ")
            fin = input("Fecha fin: ")
            if "T" not in inicio or "T" not in fin:
                print("Formato inválido. Use YYYY-MM-DDTHH:MM:SS")
                return True
            consulta = json.dumps({
                "tipo": "historico",
                "inicio": inicio,
                "fin": fin
            })
            self.req_socket.send_string(consulta)
            respuesta = self.req_socket.recv_string()
            print(respuesta)

        elif opcion == "3":
            interseccion = input("Ingrese la intersección (ej: INT_B3): ").upper()
            if not interseccion.startswith("INT_"):
                print("Formato inválido. Use INT_LetraNumero (ej: INT_B3)")
                return True
            consulta = json.dumps({
                "tipo": "decisiones_interseccion",
                "interseccion": interseccion
            })
            self.req_socket.send_string(consulta)
            respuesta = self.req_socket.recv_string()
            print(respuesta)

        elif opcion == "4":
            interseccion = input("Ingrese la intersección (ej: INT_B3): ").upper()
            if not interseccion.startswith("INT_"):
                print("Formato inválido. Use INT_LetraNumero (ej: INT_B3)")
                return True
            eje = input("Eje a priorizar - Horizontal(H) / Vertical(V): ").upper()
            if eje not in ("H", "V"):
                print("Eje inválido. Use H o V")
                return True
            duracion = input("Duración en segundos (ej: 20): ")
            try:
                duracion = int(duracion)
            except ValueError:
                print("Duración inválida. Ingrese un número")
                return True
            comando = json.dumps({
                "tipo": "prioridad",
                "interseccion": interseccion,
                "eje": eje,
                "duracion": duracion
            })
            self.req_analitica.send_string(comando)
            respuesta = self.req_analitica.recv_string()
            print(respuesta)

        elif opcion == "5":
            print("Saliendo del servicio de monitoreo...")
            return False

        else:
            print("Opción no válida, intente de nuevo")

        return True

    def run(self):

        while True:
            continuar = self.ConsultaBD()
            if not continuar:
                break

if __name__ == "__main__":
    S = Monitoreo_Consulta()
    S.run()