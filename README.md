# X1 Load Test Script

A simple **Python** script to stress-test transaction throughput on the **X1 blockchain**. It continuously generates, signs, and sends transactions from a single account to itself. You can configure concurrency, queue sizes, and RPC endpoints to push the network and gauge performance.

---

## Table of Contents
1. [Features](#features)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Usage](#usage)
6. [How It Works](#how-it-works)
7. [Output & Logs](#output--logs)
8. [Disclaimer](#disclaimer)

---

## Features

- **Asynchronous & Concurrent**  
  Uses `asyncio` and `aiohttp` for non-blocking, high-throughput network I/O.

- **Threadpool Executor for Signing**  
  Offloads CPU-bound signing to a `ThreadPoolExecutor`, ensuring minimal impact on the main event loop.

- **Adaptive Queue Management**  
  Transaction signing is paused if the queue approaches maximum capacity.

- **Multiple RPC Endpoints**  
  Distributes load across multiple RPC URLs if provided.

- **Periodic Throughput Stats**  
  Prints TPS, total successes, error count, and queue size at configurable intervals.

---

## Prerequisites

- **Python 3.8+** (Tested with 3.8, 3.9, etc.)
- The following Python packages (install via `pip install -r requirements.txt` or individually):
  - `aiohttp`
  - `orjson`
  - `base58`
  - `solders` (for Solana transaction creation and signing)

> **Note**  
> If you do not have `solders` installed, you can get it from PyPI:  
> ```bash
> pip install solders
> ```

---

## Installation

1. **Clone** this repository:
   ```bash
   git clone https://github.com/<username>/<repo_name>.git
   cd <repo_name>
   ```

2. **Install** dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   Or install each one manually:
   ```bash
   pip install aiohttp orjson base58 solders
   ```

3. **Configure** your environment (see [Configuration](#configuration)).

---

## Configuration

All configuration variables are defined at the top of the `x1_load_test.py` script:

| Variable               | Description                                                                                                               | Default                                  |
|------------------------|---------------------------------------------------------------------------------------------------------------------------|------------------------------------------|
| `LAMPORTS`             | Amount of lamports transferred per transaction.                                                                           | `1`                                      |
| `NUM_SENDERS`          | Number of concurrent sender tasks (each pinned to an RPC in round-robin fashion).                                         | `150`                                    |
| `QUEUE_MAXSIZE`        | Maximum number of signed transactions waiting in the queue.                                                               | `3000`                                   |
| `MEASUREMENT_INTERVAL` | How often (in seconds) to print throughput stats (TPS, errors, queue size, etc.).                                         | `5`                                      |
| `SOLANA_RPC_URLS`      | List of one or more RPC endpoints to submit transactions to.                                                              | `["https://rpc.testnet.x1.xyz"]`         |
| `ACCOUNT_PUBLIC`       | Base58-encoded **public key** of the funding/test account.                                                                | (add your)                                  |
| `ACCOUNT_PRIVATE`      | Base58-encoded **private key** of the same account (used to sign transactions).                                           | (add your)                                  |

### Important Notes

- **`ACCOUNT_PRIVATE`** must be valid base58-encoded bytes for the script to run. The script will raise an exception otherwise.
- By default, the script sends lamports **from the same account back to itself**. This is purely for load testing, so no net balance change should occur (aside from transaction fees).
- **Multiple RPCs** can help distribute traffic. Just add more URLs to `SOLANA_RPC_URLS`.

---

## Usage

1. **Edit** the script to set `ACCOUNT_PUBLIC` and `ACCOUNT_PRIVATE`, plus any other parameters you want to customize (e.g., `NUM_SENDERS`, `MEASUREMENT_INTERVAL`, etc.).
2. **Run**:
   ```bash
   python x1_load_test.py
   ```
3. **Watch** the console for periodic throughput stats.

---

## How It Works

1. **Fetch Blockhash**  
   A dedicated task continuously fetches the latest blockhash from one of the RPCs.  
   ```python
   asyncio.create_task(update_blockhash(session))
   ```

2. **Produce Transactions**  
   A **producer** task creates signed transactions (CPU-bound signing is offloaded to a threadpool), encoding them in base58, and placing them in a queue:
   ```python
   asyncio.create_task(transaction_producer())
   ```

3. **Send Transactions**  
   Multiple **sender** tasks (`NUM_SENDERS` by default) pull transactions off the queue and submit them to the assigned RPC endpoint:
   ```python
   sender_tasks = []
   for i in range(NUM_SENDERS):
       url = SOLANA_RPC_URLS[i % len(SOLANA_RPC_URLS)]
       sender_tasks.append(asyncio.create_task(transaction_sender(session, url)))
   ```

4. **Measure & Log**  
   A **measuring worker** prints out TPS, total successes, and error counts every `MEASUREMENT_INTERVAL` seconds:
   ```python
   asyncio.create_task(measuring_worker(MEASUREMENT_INTERVAL))
   ```

---

## Output & Logs

Every `MEASUREMENT_INTERVAL` seconds, the script prints something like:

```
[5s] TPS=2325.9, total_ok=139555, errors=0, queue_size=500
```

![image](https://github.com/user-attachments/assets/1dd9e8cc-2107-4d30-82cf-8515c511698f)


Where:
- `TPS` = **transactions per second** in the last interval
- `total_ok` = Cumulative count of successfully submitted transactions
- `errors` = Number of RPC or transaction errors encountered
- `queue_size` = Current size of the transaction queue

---

## Disclaimer

- **Use at your own risk**. This script is meant for development/testing. It can generate significant load on X1 or your chosen RPCs.
- Ensure you have adequate **testnet** funds in your account to cover transaction fees if sending more than zero lamports to external accounts. By default, it sends to itself, but you still pay the Solana network fee per transaction.
- The author(s) assume **no responsibility** for any misuse of this code or negative impacts on blockchain networks or infrastructure.

---

**Happy Testing!**  
Feel free to open issues or pull requests to improve this tool.
```
