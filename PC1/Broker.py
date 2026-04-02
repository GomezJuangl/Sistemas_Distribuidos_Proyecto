import zmq

class Broker:
    def __init__(self):
        self.context = zmq.Context()

        self.sub_socket = self.context.socket(zmq.SUB)
        self.sub_socket.bind("tcp://*:5555")
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")

        self.pub_socket = self.context.socket(zmq.PUB)
        self.pub_socket.bind("tcp://*:5556")

    def run(self):
        while True:
            mensaje = self.sub_socket.recv_string()
            self.pub_socket.send_string(mensaje)
            print("Recibido y Enviado:", mensaje)

if __name__ == "__main__":
    broker = Broker()
    broker.run()