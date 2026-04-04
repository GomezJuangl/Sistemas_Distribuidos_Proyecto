import zmq

class Broker:
    def __init__(self):
        self.context = zmq.Context()

        # SUB: recibe de los sensores (los sensores hacen connect a este puerto)
        self.sub_socket = self.context.socket(zmq.SUB)
        self.sub_socket.bind("tcp://*:5555")

        # Suscripción a los tres tópicos de sensores
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "camara")
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "gps")
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "espira_inductiva")

        # PUB: reenvía al servicio de analítica (PC2)
        self.pub_socket = self.context.socket(zmq.PUB)
        self.pub_socket.bind("tcp://*:5556")

    def run(self):
        print("[BROKER] Iniciado. Escuchando en :5555, reenviando en :5556")
        print("[BROKER] Suscrito a tópicos: camara, gps, espira_inductiva")
        while True:
            mensaje = self.sub_socket.recv_string()
            self.pub_socket.send_string(mensaje)
            print(f"📤 [BROKER] Recibido y reenviado: {mensaje[:80]}")

if __name__ == "__main__":
    broker = Broker()
    broker.run()
