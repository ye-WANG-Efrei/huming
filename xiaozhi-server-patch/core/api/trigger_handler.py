from aiohttp import web
from plugins_func.functions.play_music import handle_music_command


class TriggerHandler:
    def __init__(self, config, ws_server):
        self.config = config
        self.ws_server = ws_server
        self.auth_key = config["server"]["auth_key"]

    async def handle_post(self, request):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != self.auth_key:
            return web.Response(status=401, text="Unauthorized")

        try:
            body = await request.json()
        except Exception:
            return web.Response(status=400, text="Invalid JSON")

        device_id = body.get("device_id")
        song_name = body.get("song_name")

        if not device_id or not song_name:
            return web.Response(status=400, text="Missing device_id or song_name")

        conn = self.ws_server.connections.get(device_id)
        if not conn:
            return web.Response(status=404, text=f"Device {device_id} not connected")

        await handle_music_command(conn, f"播放音乐 {song_name}")
        return web.json_response({"status": "ok"})
