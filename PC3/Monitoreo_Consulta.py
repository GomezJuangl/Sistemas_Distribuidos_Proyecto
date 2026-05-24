import zmq
import json
from datetime import datetime

PC2_IP = "10.43.99.102"

# ─── AUTENTICACIÓN ────────────────────────────────────────────────────────────
USUARIO_VALIDO    = "admin"
CONTRASENA_VALIDA = "1234"
MAX_INTENTOS      = 3

def login():
    print("=" * 50)
    print("  SISTEMA GITU — Monitoreo y Consulta")
    print("=" * 50)
    for intento in range(1, MAX_INTENTOS + 1):
        usuario    = input("Usuario:    ").strip()
        contrasena = input("Contraseña: ").strip()
        if usuario == USUARIO_VALIDO and contrasena == CONTRASENA_VALIDA:
            print(f"\nAcceso concedido. Bienvenido, {usuario}.\n")
            return True
        restantes = MAX_INTENTOS - intento
        if restantes > 0:
            print(f"Credenciales incorrectas. Intentos restantes: {restantes}\n")
        else:
            print("Acceso denegado. Número máximo de intentos alcanzado.")
    return False
# ──────────────────────────────────────────────────────────────────────────────

class Monitoreo_Consulta():
    def __init__(self):
        self.IP_BD_PRINCIPAL = "127.0.0.1"
        self.Puerto_BDP = 5101

        self.IP_BD_REPLICA = PC2_IP
        self.Puerto_BDR = 5102

        self.TIMEOUT_MS = 3000  # Timeout para detectar caida de BD principal

        self.context = zmq.Context()

        # Socket principal (BD en PC3)
        self.req_socket = self._crear_socket_bd(self.IP_BD_PRINCIPAL, self.Puerto_BDP)

        # Socket replica (BD en PC2) - se usa si la principal no responde
        self.req_socket_replica = self._crear_socket_bd(self.IP_BD_REPLICA, self.Puerto_BDR)

        self.usando_replica = False

        self.Puerto_Analitica = 6001
        self.req_analitica = self.context.socket(zmq.REQ)
        self.req_analitica.connect(f"tcp://{PC2_IP}:{self.Puerto_Analitica}")

        self.usuario = None

    def _crear_socket_bd(self, ip, puerto):
        """Crea un socket REQ con timeout configurado."""
        sock = self.context.socket(zmq.REQ)
        sock.setsockopt(zmq.RCVTIMEO, self.TIMEOUT_MS)
        sock.setsockopt(zmq.LINGER, 0)
        sock.connect(f"tcp://{ip}:{puerto}")
        return sock

    def _reconectar_socket_principal(self):
        """Cierra y recrea el socket principal (patron Lazy Pirate)."""
        self.req_socket.close()
        self.req_socket = self._crear_socket_bd(self.IP_BD_PRINCIPAL, self.Puerto_BDP)

    def _reconectar_socket_replica(self):
        """Cierra y recrea el socket replica."""
        self.req_socket_replica.close()
        self.req_socket_replica = self._crear_socket_bd(self.IP_BD_REPLICA, self.Puerto_BDR)

    def enviar_consulta(self, consulta):
        """Envia consulta a BD principal. Si falla, usa la replica."""

        # Si ya estamos en modo replica, intentar primero la principal por si ya volvio
        if self.usando_replica:
            try:
                self.req_socket.send_string(consulta)
                respuesta = self.req_socket.recv_string()
                # Funciono, volver a modo principal
                self.usando_replica = False
                print("[MONITOREO] BD Principal recuperada. Volviendo a modo normal.")
                return respuesta
            except zmq.Again:
                self._reconectar_socket_principal()
            except Exception:
                self._reconectar_socket_principal()

        if not self.usando_replica:
            # Intentar con BD principal
            try:
                self.req_socket.send_string(consulta)
                respuesta = self.req_socket.recv_string()
                return respuesta
            except zmq.Again:
                print("[MONITOREO] BD Principal no responde. Cambiando a BD Replica...")
                self._reconectar_socket_principal()
                self.usando_replica = True
            except Exception as e:
                print(f"[MONITOREO] Error con BD Principal: {e}. Cambiando a BD Replica...")
                self._reconectar_socket_principal()
                self.usando_replica = True

        # Usar replica
        try:
            self.req_socket_replica.send_string(consulta)
            respuesta = self.req_socket_replica.recv_string()
            return respuesta
        except zmq.Again:
            self._reconectar_socket_replica()
            return "Error: Ni la BD Principal ni la BD Replica respondieron."
        except Exception as e:
            self._reconectar_socket_replica()
            return f"Error con BD Replica: {e}"



    def ConsultaBD(self):
        # Mostrar si estamos usando la replica
        modo = "(REPLICA)" if self.usando_replica else "(PRINCIPAL)"
        print(f"\n{'=' * 50}")
        print(f"  SERVICIO DE MONITOREO Y CONSULTA {modo}")
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
            respuesta = self.enviar_consulta(consulta)
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
            respuesta = self.enviar_consulta(consulta)
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
            respuesta = self.enviar_consulta(consulta)
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
            ts_envio = datetime.now().isoformat(timespec="milliseconds")
            print(f"[VD2-INICIO] {ts_envio} — comando enviado a analítica")
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
    if not login():
        exit(1)
    S = Monitoreo_Consulta()
    S.run()