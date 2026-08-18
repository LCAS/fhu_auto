import time

import roslibpy


class DoorClient:

    def __init__(self, ip='10.8.0.48', port=9090):
        self.client = roslibpy.Ros(host=ip, port=port)
        self.client.run()
        self.command_topic = roslibpy.Topic(self.client, '/command', 'std_msgs/String')

    def open(self):
        self.command_topic.publish(roslibpy.Message({'data': 'up'}))
        print('opening door.')

    def close(self):
        self.command_topic.publish(roslibpy.Message({'data': 'down'}))
        print('closing door.')
    time.sleep(1)

    def shutdown(self):
        self.command_topic.unadvertise()
        self.client.terminate()

if __name__ == '__main__':
    print('Running...')
    dc = DoorClient()
    dc.close()
    dc.shutdown()
