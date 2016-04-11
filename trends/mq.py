import logging

from amqplib import client_0_8 as amqp

import config
import exceptions

class MQ(object):
    def __init__(self):
        c = config.Config()
        self.config = c.cfg
        self.log = logging.getLogger('mq')
        self.consumer = None
        self.callback = None
        self.producer = None

    def init_consumer(self, callback):
        """Initialize a consumer to read from a queue."""
        try:
            self.consumer = Consumer(
                self.config.get('rabbitmq', 'host'),
                self.config.get('rabbitmq', 'userid'),
                self.config.get('rabbitmq', 'password'))
            self.consumer.declare_exchange(exchange_name='trends')
            self.consumer.declare_queue(queue_name='posts',
                                        routing_key='posts')
            self.callback = callback
            self.consumer.add_consumer(self.msg_callback)
        except amqp.AMQPException:
            self.log.error('Error configuring the consumer')
            raise exceptions.MQError()

    def init_producer(self):
        """Initialize a producer to publish messages."""
        try:
            self.producer = Producer('trends',
                self.config.get('rabbitmq', 'host'),
                self.config.get('rabbitmq', 'userid'),
                self.config.get('rabbitmq', 'password'))
        except amqp.AMQPException:
            self.log.error('Error configuring the producer')
            raise exceptions.MQError()

    def msg_callback(self, message):
        self.consumer.channel.basic_ack(message.delivery_tag)
        self.callback(message)

class Consumer(object):
    def __init__(self, host, userid, password):
        """
        Constructor. Initiate connection with RabbitMQ server.
        """
        self.connection = amqp.Connection(host=host, userid=userid, password=password, virtual_host="/", insist=False)
        self.channel = self.connection.channel()

    def close(self):
        """
        Close channel and connection.
        """
        self.channel.close()
        self.connection.close()

    def declare_exchange(self, exchange_name, durable=True, auto_delete=False):
        """
        Create exchange.
        """
        self.exchange_name = exchange_name
        self.channel.exchange_declare(exchange=self.exchange_name,
            type='direct', durable=durable, auto_delete=auto_delete)

    def declare_queue(self, queue_name, routing_key, durable=True,
        exclusive=False, auto_delete=False):
        """
        Create a queue and bind it to the exchange.
        """
        self.queue_name = queue_name
        self.routing_key = routing_key
        self.channel.queue_declare(queue=self.queue_name, durable=durable,
            exclusive=exclusive, auto_delete=auto_delete)
        self.channel.queue_bind(queue=self.queue_name,
            exchange=self.exchange_name, routing_key=self.routing_key)

    def wait(self):
        """
        Wait for activity on the channel.
        """
        while True:
            self.channel.wait()

    def add_consumer(self, callback, queue_name=None, consumer_tag='callback'):
        """
        Create a consumer and register a function to be called when
        a message is consumed
        """
        if hasattr(self, 'queue_name') or queue_name:
            self.consumer_tag = consumer_tag
            self.channel.basic_consume(
                queue=getattr(self, 'queue_name', queue_name),
                callback=callback,
                consumer_tag=consumer_tag)

    def del_consumer(self, consumer_tag='callback'):
        """
        Cancel a consumer.
        """
        self.channel.basic_cancel(consumer_tag)


class Producer(object):
    def __init__(self, exchange_name, host, userid, password):
        """
        Constructor. Initiate connection with the RabbitMQ server.
        """
        self.exchange_name = exchange_name
        self.connection = amqp.Connection(
            host=host, userid=userid, password=password, virtual_host="/",
            insist=False)
        self.channel = self.connection.channel()

    def publish(self, message, routing_key):
        """
        Publish message to exchange using routing key
        """
        msg = amqp.Message(message)
        msg.properties["content_type"] = "text/plain"
        msg.properties["delivery_mode"] = 2
        self.channel.basic_publish(exchange=self.exchange_name,
                         routing_key=routing_key,
                         msg=msg)
    def close(self):
        """
        Close channel and connection
        """
        self.channel.close()
        self.connection.close()


