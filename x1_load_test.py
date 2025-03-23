import asyncio
import aiohttp
import orjson
import base58
import random
import concurrent.futures
from solders.transaction import Transaction
from solders.system_program import TransferParams, transfer
from solders.keypair import Keypair
from solders.message import Message
from solders.hash import Hash


# ========================================
# Configuration
# ========================================
LAMPORTS = 1                   # Minimum lamports per transaction
NUM_SENDERS = 150              # Number of concurrent sender tasks
QUEUE_MAXSIZE = 3000           # Maximum number of signed transactions in-flight
MEASUREMENT_INTERVAL = 5       # Print stats every N seconds

# If you have multiple RPCs, list them here:
SOLANA_RPC_URLS = [
    "https://rpc.testnet.x1.xyz"
    # Add more RPC URLs if you want to distribute load, but you can leave this default setting
]

# Use the same account for both testing and funding
ACCOUNT_PUBLIC = ""
ACCOUNT_PRIVATE = ""

# Validate private key
try:
    keypair = Keypair.from_bytes(base58.b58decode(ACCOUNT_PRIVATE))
except Exception as e:
    raise ValueError(f"Invalid ACCOUNT_PRIVATE provided: {e}")

# ========================================
# Global shared state
# ========================================
total_success = 0
error_count = 0
current_blockhash = None
tx_queue = asyncio.Queue(maxsize=QUEUE_MAXSIZE)

# Prepare a dedicated executor for CPU-bound transaction signing
executor = concurrent.futures.ThreadPoolExecutor(max_workers=NUM_SENDERS * 2)

# Prebuild one transfer instruction (from self -> self)
transfer_inst = transfer(
    TransferParams(
        from_pubkey=keypair.pubkey(),
        to_pubkey=keypair.pubkey(),
        lamports=LAMPORTS
    )
)

def create_signed_transaction(blockhash: Hash) -> str:
    """
    Create & sign a single transaction, then return base58-encoded bytes.
    """
    # Build message
    msg = Message.new_with_blockhash([transfer_inst], keypair.pubkey(), blockhash)
    tx = Transaction([keypair], msg, blockhash)
    tx.sign([keypair], blockhash)  # One sign call

    # Serialize
    raw_tx = bytes(tx)
    encoded_tx = base58.b58encode(raw_tx).decode("utf-8")
    return encoded_tx

# -----------------------------------------------
# Blockhash Updater
# -----------------------------------------------
async def update_blockhash(session: aiohttp.ClientSession):
    """
    Continuously fetch the latest blockhash from one (or multiple) RPCs.
    Updates the global `current_blockhash`.
    """
    global current_blockhash
    while True:
        rpc_url = random.choice(SOLANA_RPC_URLS)
        try:
            # Build a minimal JSON request with orjson
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getLatestBlockhash",
                "params": []
            }
            data_bytes = orjson.dumps(payload)
            async with session.post(
                    rpc_url,
                    data=data_bytes,
                    headers={"Content-Type": "application/json"},  # Important!
                    timeout=3
            ) as response:
                resp_data = await response.read()

                # DEBUG: Uncomment to see raw responses
                # print(f"DEBUG: RPC response from {rpc_url}: {resp_data}")

                data = orjson.loads(resp_data)
                blockhash_str = data["result"]["value"]["blockhash"]
                new_hash = Hash.from_string(blockhash_str)
                if new_hash != current_blockhash:
                    current_blockhash = new_hash
                    # DEBUG: Uncomment if you want to see blockhash updates
                    # print(f"DEBUG: Updated blockhash to {current_blockhash}")
        except Exception as e:
            # DEBUG: Uncomment to see error details
            # print(f"DEBUG: Error fetching blockhash from {rpc_url} -> {e}")
            pass

        await asyncio.sleep(1)

# -----------------------------------------------
# Transaction Producer
# -----------------------------------------------
async def transaction_producer():
    """
    Continuously produce signed transactions (base58-encoded).
    If queue is near capacity, wait briefly to avoid overfilling.
    """
    loop = asyncio.get_running_loop()
    while True:
        while current_blockhash is None:
            await asyncio.sleep(0.0005)

        old_hash = current_blockhash
        # Produce until blockhash changes
        while old_hash == current_blockhash:
            if tx_queue.qsize() >= QUEUE_MAXSIZE * 0.8:
                await asyncio.sleep(0.0005)
                continue

            try:
                # CPU-bound signing in threadpool
                encoded_tx = await loop.run_in_executor(
                    executor, create_signed_transaction, old_hash
                )
                await tx_queue.put(encoded_tx)
            except Exception:
                continue

# -----------------------------------------------
# Transaction Sender
# -----------------------------------------------
async def transaction_sender(session: aiohttp.ClientSession, rpc_url: str):
    """
    Continuously fetch signed transactions from the queue and submit them.
    Each sender task is pinned to a single RPC (round-robin assigned).
    """
    global total_success, error_count
    while True:
        try:
            encoded_tx = await tx_queue.get()
        except Exception:
            continue

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "sendTransaction",
            "params": [encoded_tx]
        }
        data_bytes = orjson.dumps(payload)

        try:
            async with session.post(
                    rpc_url,
                    data=data_bytes,
                    headers={"Content-Type": "application/json"},  # Important!
                    timeout=3
            ) as response:
                resp_data = await response.read()
                result = orjson.loads(resp_data)

                if "error" in result:
                    err_msg = result["error"].get("message", "").lower()
                    if "blockhash" not in err_msg and "expired" not in err_msg:
                        error_count += 1
                else:
                    total_success += 1

        except Exception:
            error_count += 1

# -----------------------------------------------
# Measurement / Stats Logger
# -----------------------------------------------
async def measuring_worker(interval=5):
    """
    Prints throughput stats every `interval` seconds.
    Minimal text to reduce overhead.
    """
    global total_success, error_count
    prev_success = 0
    while True:
        await asyncio.sleep(interval)
        current = total_success
        delta = current - prev_success
        tps = delta / interval
        qsize = tx_queue.qsize()

        print(
            f"[{interval}s] TPS={tps:.1f}, total_ok={current}, "
            f"errors={error_count}, queue_size={qsize}"
        )
        prev_success = current

# -----------------------------------------------
# Main Execution
# -----------------------------------------------
async def main():
    # Create one shared ClientSession with unlimited TCP connections
    connector = aiohttp.TCPConnector(limit=0)
    async with aiohttp.ClientSession(connector=connector) as session:
        # Start tasks
        asyncio.create_task(update_blockhash(session))
        asyncio.create_task(transaction_producer())
        asyncio.create_task(measuring_worker(MEASUREMENT_INTERVAL))

        # Round-robin assignment of RPC URLs for each sender
        sender_tasks = []
        for i in range(NUM_SENDERS):
            url = SOLANA_RPC_URLS[i % len(SOLANA_RPC_URLS)]
            sender_tasks.append(
                asyncio.create_task(transaction_sender(session, url))
            )

        await asyncio.gather(*sender_tasks)

if __name__ == "__main__":
    asyncio.run(main())
