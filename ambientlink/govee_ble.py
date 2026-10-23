"""H600B encrypted BLE transport; no cloud account or firmware modification.

Protocol reference: egold555/Govee-Reverse-Engineering Products/H600B.md
(research by mpalczew). Keys are protocol constants; session keys stay in RAM.
"""
import asyncio
from functools import reduce

from bleak import BleakClient, BleakScanner
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

WRITE = "00010203-0405-0607-0809-0a0b0c0d2b11"
NOTIFY = "00010203-0405-0607-0809-0a0b0c0d2b10"
AUTH_KEY = b"MakingLifeSmarte"


async def discover_bulbs(bulbs):
    """Resolve disconnected bulbs in one scan instead of three implicit scans."""
    missing = [b for b in bulbs if not b.connected]
    if not missing:
        return
    devices = await bounded(BleakScanner.discover(timeout=4), 6)
    found = {d.address.upper(): d for d in devices}
    for bulb in missing:
        # A short general scan can miss a connectable H600B. Keep its previously
        # resolved device, or let Bleak perform bounded address-specific discovery.
        # Absence from one advertisement window is not proof it is unavailable.
        bulb.device = found.get(bulb.address.upper(), bulb.device)


async def bounded(operation, timeout):
    """WinRT cancellation may await native cleanup indefinitely; never hold the
    command lock waiting for that cleanup after an I/O deadline has expired.
    """
    task = asyncio.ensure_future(operation)
    def consume(done):
        if not done.cancelled(): done.exception()
    try:
        done, _ = await asyncio.wait({task},timeout=timeout)
        if not done:
            task.cancel()
            task.add_done_callback(consume)
            raise TimeoutError("Bluetooth operation timed out")
        if task.cancelled():
            # WinRT may cancel an operation after a link loss without cancelling
            # our caller. Treat that as a recoverable transport failure.
            raise ConnectionError("Bluetooth operation cancelled by adapter")
        return task.result()
    except asyncio.CancelledError:
        task.cancel()
        task.add_done_callback(consume)
        raise


def rc4(key, data):
    permutation = list(range(256))
    j = 0
    for i in range(256):
        j = (j + permutation[i] + key[i % len(key)]) % 256
        permutation[i], permutation[j] = permutation[j], permutation[i]
    i = j = 0
    result = bytearray()
    for byte in data:
        i = (i + 1) % 256
        j = (j + permutation[i]) % 256
        permutation[i], permutation[j] = permutation[j], permutation[i]
        result.append(byte ^ permutation[(permutation[i] + permutation[j]) % 256])
    return bytes(result)


def encode(payload, key):
    if not 2 <= len(payload) <= 19 or len(key) != 16:
        raise ValueError("Invalid packet")
    plain = bytes(payload).ljust(19, b"\0")
    plain += bytes([reduce(int.__xor__, plain)])
    cipher = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return cipher.update(plain[:16]) + cipher.finalize() + rc4(key, plain[16:])


def decode(packet, key):
    if len(packet) != 20 or len(key) != 16:
        raise ValueError("Invalid encrypted packet")
    cipher = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    plain = cipher.update(packet[:16]) + cipher.finalize() + rc4(key, packet[16:])
    if reduce(int.__xor__, plain) != 0:
        raise ValueError("Packet checksum mismatch")
    return plain


class Bulb:
    def __init__(self, address):
        self.address = address
        self.client = None
        self.device = None
        self.key = None
        self.queue = asyncio.Queue(maxsize=64)
        self.io = asyncio.Lock()
        self.speed_request = None
        self.color_writes = 0
        self.control_allowed = lambda: True

    @property
    def connected(self):
        return self.key is not None and self.client is not None and self.client.is_connected

    def receive(self, _, data):
        if self.queue.full():
            self.queue.get_nowait()
        self.queue.put_nowait(bytes(data))

    async def wait(self, key, prefix, timeout=3):
        async with asyncio.timeout(timeout):
            while True:
                packet = await self.queue.get()
                try:
                    plain = decode(packet, key)
                except ValueError:
                    continue
                if plain.startswith(prefix):
                    return plain

    async def connect(self):
        if not self.control_allowed(): raise RuntimeError('Lighting lease unavailable')
        if self.connected:
            return
        await self.close()
        self.client = BleakClient(self.device or self.address, timeout=12,
                                  winrt={"use_cached_services": False})
        stage = "connect"
        try:
            async with asyncio.timeout(22):
                await bounded(self.client.connect(),18)
                stage = "notifications"
                await bounded(self.client.start_notify(NOTIFY, self.receive),3)
                await asyncio.sleep(.12)
                stage = "authentication"
                await bounded(self.client.write_gatt_char(WRITE, encode(b"\xe7\x01", AUTH_KEY), response=False),3)
                reply = await self.wait(AUTH_KEY, b"\xe7\x01")
                self.key = reply[2:18]
                await bounded(self.client.write_gatt_char(WRITE, encode(b"\xe7\x02", AUTH_KEY), response=False),3)
                try:
                    await self.wait(AUTH_KEY, b"\xe7\x02", .8)
                except TimeoutError:
                    pass
                await asyncio.sleep(.08)
        except TimeoutError as error:
            await self.close()
            raise TimeoutError(f"H600B {self.address[-5:]}: {stage} timed out") from error
        except BaseException:
            await self.close()
            raise

    async def close(self):
        self.streaming(False)
        client, self.client, self.key = self.client, None, None
        if client:
            try:
                await bounded(client.disconnect(), 4)
            except Exception:
                pass
        while not self.queue.empty():
            self.queue.get_nowait()

    def streaming(self, enabled):
        if self.speed_request:
            self.speed_request.close()
            self.speed_request = None
        if enabled and self.connected:
            try:
                from winrt.windows.devices.bluetooth import BluetoothLEPreferredConnectionParameters as P
                self.speed_request = self.client._backend._requester.request_preferred_connection_parameters(P.throughput_optimized)
            except (AttributeError, OSError):
                pass  # Unsupported adapters retain normal connection settings.

    async def send(self, payload, response=True):
        async with self.io:
            await self.send_unlocked(payload,response)

    async def send_unlocked(self, payload, response=True):
        if not self.control_allowed(): raise RuntimeError('Lighting lease unavailable')
        if self.key is None or not self.client or not self.client.is_connected:
            raise ConnectionError("Bulb disconnected")
        # ATT acknowledgement applies backpressure instead of filling the
        # controller's unacknowledged-write queue with obsolete video frames.
        await bounded(self.client.write_gatt_char(WRITE, encode(payload, self.key), response=response), 3)

    async def query(self, opcode):
        # No outstanding queries: discard old notifications before requesting state.
        async with self.io:
            while not self.queue.empty():
                self.queue.get_nowait()
            await self.send_unlocked(bytes([0xaa, opcode]),False)
            return await self.wait(self.key, bytes([0xaa, opcode]))

    async def status(self):
        power = await self.query(1)
        brightness = await self.query(4)
        color = await self.query(5)
        return {"power": bool(power[2]), "brightness": brightness[2],
                "rgb": list(color[3:6]) if color[2] in (2, 13) else None,
                "colorMode": color[2]}

    async def read_power(self):
        reply = await self.query(1)
        if reply[2] not in (0, 1):
            raise ValueError("Invalid power reply")
        return bool(reply[2])

    async def power(self, enabled):
        await self.send(bytes([0x33, 1, int(enabled)]))

    async def color(self, rgb):
        if len(rgb) != 3 or any(type(c) is not int or not 0 <= c <= 255 for c in rgb):
            raise ValueError("Invalid RGB")
        self.color_writes += 1
        # Wait for every ATT acknowledgement. Unacknowledged colors can accumulate
        # in the controller even when Python keeps only its newest frame.
        await self.send(bytes([0x33, 5, 13, *rgb]),response=True)

    async def brightness(self, value):
        if type(value) is not int or not 0 <= value <= 100:
            raise ValueError("Invalid brightness")
        await self.send(bytes([0x33, 4, value]))
