import asyncio
import socket
import sys

FORWARD_RULES = [
    ("0.0.0.0", 80, "127.0.0.1", 80),
    ("0.0.0.0", 8080, "127.0.0.1", 8080),
]

async def forward_stream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

async def handle_client(local_reader: asyncio.StreamReader, local_writer: asyncio.StreamWriter, target_host: str, target_port: int):
    try:
        remote_reader, remote_writer = await asyncio.open_connection(target_host, target_port)
    except Exception as exc:
        local_writer.close()
        await local_writer.wait_closed()
        return

    await asyncio.gather(
        forward_stream(local_reader, remote_writer),
        forward_stream(remote_reader, local_writer),
        return_exceptions=True
    )

async def main():
    servers = []
    for listen_host, listen_port, target_host, target_port in FORWARD_RULES:
        try:
            server = await asyncio.start_server(
                lambda r, w, th=target_host, tp=target_port: handle_client(r, w, th, tp),
                listen_host,
                listen_port,
                reuse_address=True
            )
            servers.append(server)
            print(f"[FORWARD] {listen_host}:{listen_port} -> {target_host}:{target_port}")
        except Exception as exc:
            # Try specific external IP fallback if 0.0.0.0 has collision
            print(f"[WARN] Failed to bind {listen_host}:{listen_port}: {exc}")
            try:
                server = await asyncio.start_server(
                    lambda r, w, th=target_host, tp=target_port: handle_client(r, w, th, tp),
                    "1.250.5.161",
                    listen_port,
                    reuse_address=True
                )
                servers.append(server)
                print(f"[FORWARD] 1.250.5.161:{listen_port} -> {target_host}:{target_port}")
            except Exception as e2:
                print(f"[ERROR] Failed to bind fallback: {e2}")

    if not servers:
        print("[ERROR] No servers started", file=sys.stderr)
        return 1

    print("[READY] All port forwarders active.")
    await asyncio.gather(*(s.serve_forever() for s in servers))

if __name__ == "__main__":
    asyncio.run(main())
