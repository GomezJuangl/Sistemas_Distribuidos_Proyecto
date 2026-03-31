import zmq

class Broker:
    def __init__(self):
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.SUB)
        self.socket.bind("tcp://*:5555")
        self.socket.setsockopt_string(zmq.SUBSCRIBE, "")

    def run(self):
        while True:
            mensaje = self.socket.recv_string()
            print("Recibido:", mensaje)

if __name__ == "__main__":
    broker = Broker()
    broker.run()