import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

class AlertConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Get user from session
        user = self.scope.get("user")
        if user and user.is_authenticated:
            self.user_id = user.id
            self.group_name = f"user_{self.user_id}"
            
            # Join user group
            await self.channel_layer.group_add(
                self.group_name,
                self.channel_name
            )
            
            await self.accept()
        else:
            await self.close()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            # Leave user group
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type', '')
            
            if message_type == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': text_data_json.get('timestamp', '')
                }))
        except json.JSONDecodeError:
            pass

    async def send_alert_notification(self, event):
        """Send alert notification to WebSocket"""
        message = event['message']
        
        await self.send(text_data=json.dumps({
            'type': 'alert_notification',
            'alert': message
        }))

class CameraConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Get user from session
        user = self.scope.get("user")
        if user and user.is_authenticated:
            self.user_id = user.id
            self.camera_id = self.scope['url_route']['kwargs']['camera_id']
            self.group_name = f"camera_{self.user_id}_{self.camera_id}"
            
            # Join camera group
            await self.channel_layer.group_add(
                self.group_name,
                self.channel_name
            )
            
            await self.accept()
        else:
            await self.close()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            # Leave camera group
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    async def camera_frame(self, event):
        """Send camera frame to WebSocket"""
        frame_data = event['frame']
        await self.send(bytes_data=frame_data)

def send_frame_to_user(user_id, camera_id, frame_data):
    """Helper function to send frame to user's camera group"""
    channel_layer = get_channel_layer()
    group_name = f"camera_{user_id}_{camera_id}"
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            'type': 'camera_frame',
            'frame': frame_data
        }
    )