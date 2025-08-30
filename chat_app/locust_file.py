import time
import json
import random
from websocket import create_connection, WebSocket
from locust import User, task, events, HttpUser, between, constant
from locust.exception import StopUser

# This custom client class is a wrapper around the `websocket-client` library
# that reports events (successes and failures) to Locust.
# This is a key step since Locust is not natively designed for WebSockets.
class WebSocketClient(object):
    """
    A simple wrapper around the `websocket` library to be used as a Locust client.
    """
    def __init__(self, host):
        self.host = host
        self.ws = None
        self.is_connected = False

    def connect(self, path, sslopt=None, headers=None, name="Connect"):
        """
        Establishes a WebSocket connection.
        Reports success or failure to Locust's event handler.
        """
        start_time = time.perf_counter()
        try:
            # Create a WebSocket connection
            self.ws = create_connection(
                f"{self.host}{path}",
                sslopt=sslopt,
                headers=headers
            )
            self.is_connected = True
            total_time = (time.perf_counter() - start_time) * 1000
            events.request.fire(
                request_type="WebSocket",
                name=name,
                response_time=total_time,
                response_length=0,
            )
            return True
        except Exception as e:
            total_time = (time.perf_counter() - start_time) * 1000
            events.request.fire(
                request_type="WebSocket",
                name=name,
                response_time=total_time,
                response_length=0,
                exception=e,
            )
            return False

    def send(self, message, name="Send Message"):
        """
        Sends a message over the WebSocket.
        Reports success or failure to Locust's event handler.
        """
        start_time = time.perf_counter()
        try:
            self.ws.send(message)
            total_time = (time.perf_counter() - start_time) * 1000
            events.request.fire(
                request_type="WebSocket",
                name=name,
                response_time=total_time,
                response_length=len(message),
            )
        except Exception as e:
            total_time = (time.perf_counter() - start_time) * 1000
            events.request.fire(
                request_type="WebSocket",
                name=name,
                response_time=total_time,
                response_length=0,
                exception=e,
            )
            # If sending fails, we assume the connection is broken and raise an exception
            self.is_connected = False
            raise StopUser()

    def receive(self, name="Receive Message"):
        """
        Receives a message from the WebSocket.
        Reports success or failure to Locust's event handler.
        """
        start_time = time.perf_counter()
        response_length = 0
        try:
            response = self.ws.recv()
            if response is None:
                raise Exception("Received None from WebSocket")
            
            response_length = len(response)
            total_time = (time.perf_counter() - start_time) * 1000
            events.request.fire(
                request_type="WebSocket",
                name=name,
                response_time=total_time,
                response_length=response_length,
            )
            return response
        except Exception as e:
            total_time = (time.perf_counter() - start_time) * 1000
            events.request.fire(
                request_type="WebSocket",
                name=name,
                response_time=total_time,
                response_length=response_length,
                exception=e,
            )
            # If receiving fails, stop the user as the connection is likely dead
            self.is_connected = False
            raise StopUser()

    def close(self, name="Disconnect"):
        """
        Closes the WebSocket connection.
        """
        start_time = time.perf_counter()
        try:
            self.ws.close()
        finally:
            total_time = (time.perf_counter() - start_time) * 1000
            events.request.fire(
                request_type="WebSocket",
                name=name,
                response_time=total_time,
                response_length=0,
            )
            self.is_connected = False

# A custom User class that uses our custom client
class WebSocketUser(HttpUser):
    # This attribute makes Locust use our custom client instead of the default HttpUser client
    abstract = True

    def __init__(self, *args, **kwargs):
        super(WebSocketUser, self).__init__(*args, **kwargs)
        # Create a new instance of our custom client for each user
        self.client = WebSocketClient(self.host)

# Define the user behavior for the load test
class MyWebSocketUser(WebSocketUser):
    # Set the wait time between tasks in seconds
    wait_time = constant(0)

    host = "ws://localhost:8000"  # A public WebSocket echo server for testing

    def on_start(self):
        """
        This method is called when a new user starts.
        It's a good place to establish the WebSocket connection.
        """
        self.client.connect("/ws/")

    # This task simulates sending a message without first joining
    @task
    def connected(self):
        if not self.client.is_connected:
            self.client.connect("")
    
    def on_stop(self):
        """
        This method is called when a user stops.
        It's a good place to close the connection gracefully.
        """
        self.client.close()
