import asyncio
import json
import os
from flask_log_server import (LOGS, run_flask, should_stop, set_wallet_status, log_wallet, WALLET_STATUS, GLOBAL_LOOP_EVENT, GLOBAL_LOOP_INTERVAL, LOOP_INTERVALS, GLOBAL_CONFIG, config_lock)
import threading
import aiohttp
import requests
from eth_account import Account
from eth_account.messages import encode_defunct
from datetime import datetime
from web3 import Web3, HTTPProvider
import random
import time
from eth_abi import encode as abi_encode
from colorama import init, Fore, Style
from config import *
from abi import ERC20_ABI, SWAP_ROUTER_ABI, POSITION_MANAGER_ABI

init(autoreset=True)

class Colors:
    beige = Fore.LIGHTYELLOW_EX
    blue = Fore.LIGHTBLUE_EX
    green = Fore.GREEN
    red = Fore.RED
    cyan = Fore.CYAN
    yellow = Fore.YELLOW
    bold = Style.BRIGHT
    reset = Style.RESET_ALL

w3 = Web3(Web3.HTTPProvider(PHAROS_RPC))

erc20_abi = json.loads(ERC20_ABI)
swap_router_abi = json.loads(SWAP_ROUTER_ABI)

flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()
time.sleep(2)

def log_wallet(address, msg):
    print(f"[{address[:8]}] {msg}")
    LOGS.setdefault(address, []).append(msg)
    if len(LOGS[address]) > 1000:
        LOGS[address] = LOGS[address][-1000:]

def load_private_keys():
    if not os.path.exists(KEYS_PATH):
        print(f"[!] File {KEYS_PATH} not found!")
        return []
    with open(KEYS_PATH, "r") as f:
        keys = [line.strip() for line in f if line.strip()]
    return keys

def load_proxies(filename=None):
    if filename is None:
        filename = PROXY_PATH
    try:
        with open(filename, "r") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"[!] File {filename} not found — launching without proxy")
        return []

async def safe_json(resp, context=""):
    try:
        return await resp.json(content_type=None)
    except Exception:
        print(f"[!] Response not JSON for {context}")
        return None

def normalize_proxy(proxy: str) -> str:
    if proxy and not proxy.startswith("http"):
        return "http://" + proxy
    return proxy

def get_w3(proxy: str = None) -> Web3:
    if proxy:
        session = requests.Session()
        session.proxies = {"http": proxy, "https": proxy}
        provider = HTTPProvider(PHAROS_RPC, session=session)
        return Web3(provider)
    else:
        return Web3(Web3.HTTPProvider(PHAROS_RPC))

def get_aiohttp_proxy(proxy: str = None) -> str | None:
    return proxy if proxy else None

def encode_exact_input_single(token_in, token_out, fee, recipient, amount_in, amount_out_min, sqrt_price_limit=0):
    selector = bytes.fromhex("04e45aaf")
    types = [
        "address", "address", "uint24", "address", "uint256", "uint256", "uint160"
    ]
    args = [
        Web3.to_checksum_address(token_in),
        Web3.to_checksum_address(token_out),
        fee,
        Web3.to_checksum_address(recipient),
        amount_in,
        amount_out_min,
        sqrt_price_limit
    ]
    return selector + abi_encode(types, args)

async def claim_faucet(pk, proxy=None):
    proxy_url = normalize_proxy(proxy) if proxy else None
    timeout = aiohttp.ClientTimeout(total=30)
    acct = Account.from_key(pk)
    address = acct.address
    def _log(msg):
        log_wallet(address, msg)
    message = encode_defunct(text="pharos")
    signed_message = Account.sign_message(message, pk)
    signature = signed_message.signature.hex()
    login_url = f"{PHAROS_API}/user/login?address={address}&signature={signature}&invite_code=g4oanA8cB1e82QD1"
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.8",
        "authorization": "Bearer null",
        "sec-ch-ua": '"Chromium";v="136", "Brave";v="136", "Not.A/Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "sec-gpc": "1",
        "Referer": "https://testnet.pharosnetwork.xyz/",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "User-Agent": "Mozilla/5.0 (compatible)"
    }
    max_retries = 3
    attempt = 0
    while attempt < max_retries:
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(login_url, headers=headers, proxy=proxy_url) as resp:
                    login_data = await safe_json(resp, f"login {address} (proxy={proxy_url})")
                if not login_data or login_data.get("code") != 0 or "jwt" not in login_data.get("data", {}):
                    _log(f"[!] Login failed: {login_data}")
                    attempt += 1
                    await asyncio.sleep(2)
                    continue
                jwt = login_data["data"]["jwt"]
                _log(f"[+] JWT received: {jwt[:16]}...")
                faucet_headers = dict(headers)
                faucet_headers["authorization"] = f"Bearer {jwt}"
                async with session.get(
                    f"{PHAROS_API}/faucet/status?address={address}",
                    headers=faucet_headers,
                    proxy=proxy_url
                ) as resp:
                    status_data = await safe_json(resp, f"faucet status {address}")
                if not status_data:
                    attempt += 1
                    await asyncio.sleep(2)
                    continue
                if status_data.get("data", {}).get("is_able_to_faucet"):
                    async with session.post(
                        f"{PHAROS_API}/faucet/daily?address={address}",
                        headers=faucet_headers,
                        proxy=proxy_url
                    ) as resp:
                        claim_data = await safe_json(resp, f"faucet claim {address}")
                    if resp.status == 200 and claim_data and claim_data.get("code") == 0:
                        _log(f"✅ Faucet successfully claimed for {address}")
                        return True
                    else:
                        _log(f"❌ Error claiming faucet: {claim_data}")
                        attempt += 1
                        await asyncio.sleep(2)
                        continue
                else:
                    next_ts = status_data.get("data", {}).get("avaliable_timestamp")
                    if next_ts:
                        readable = datetime.fromtimestamp(next_ts).strftime('%Y-%m-%d %H:%M:%S')
                        _log(f"🕐 Faucet will be available at: {readable}")
                    else:
                        _log("🚫 Faucet is not available")
                    return False
        except Exception as e:
            attempt += 1
            proxy_info = f" (proxy={proxy_url})" if proxy_url else ""
            _log(f"❌ Error while requesting faucet for {address}{proxy_info}: {e}")
            await asyncio.sleep(2)
    _log(f"❌ All attempts to claim faucet for {address} failed after {max_retries} tries.")
    return False


async def send_10_txs(private_key, proxy=None):
    loop = asyncio.get_running_loop()
    w3 = await loop.run_in_executor(None, get_w3, proxy)
    acct = Account.from_key(private_key)
    address = acct.address
    def _log(msg):
        log_wallet(address, msg)
    _log(f"▶️ Sending 10 transactions from address: {address}")
    nonce = await loop.run_in_executor(None, w3.eth.get_transaction_count, address)
    for i in range(10):
        if should_stop(address):
            log_wallet(address, f"⏹️ Sending stopped at TX {i + 1}")
            break
        to_address = get_random_eth_address()
        value = w3.to_wei(random.uniform(0.00001, 0.0001), 'ether')
        tx = {
            'nonce': nonce + i,
            'to': to_address,
            'value': value,
            'gas': 21000,
            'gasPrice': 0,
            'chainId': 688688,
        }
        max_attempts = 3
        attempt = 0
        while attempt < max_attempts:
            attempt += 1
            try:
                signed_tx = await loop.run_in_executor(None, w3.eth.account.sign_transaction, tx, private_key)
                tx_hash = await loop.run_in_executor(None, w3.eth.send_raw_transaction, signed_tx.raw_transaction)
                _log(f"[{i + 1}/10] TX sent → {to_address} (attempt {attempt})")
                _log(f"⏳ Waiting for confirmation...")
                receipt = await loop.run_in_executor(None, w3.eth.wait_for_transaction_receipt, tx_hash, 120)
                if receipt.status == 1:
                    _log(f"✅ Confirmed in block {receipt.blockNumber}: {w3.to_hex(tx_hash)}")
                else:
                    _log(f"❌ Transaction failed! {w3.to_hex(tx_hash)}")
                break
            except Exception as e:
                is_replay = False
                if isinstance(e, dict) and e.get("message") and "TX_REPLAY_ATTACK" in e["message"]:
                    is_replay = True
                elif hasattr(e, "args") and e.args and isinstance(e.args[0], dict):
                    if "message" in e.args[0] and "TX_REPLAY_ATTACK" in e.args[0]["message"]:
                        is_replay = True
                _log(f"[{i + 1}/10] ❌ Error while sending (attempt {attempt}): {e}")
                if is_replay:
                    _log(f"[{i + 1}/10] ⚠️ TX_REPLAY_ATTACK — skipping further retries for this transaction.")
                    break
                if attempt == max_attempts:
                    _log(f"[{i + 1}/10] ❌ Max retry attempts reached, skipping this transaction.")
                else:
                    await asyncio.sleep(3)
        if i != 9:
            delay = random.randint(5, 15)
            _log(f"⏳ Waiting {delay} sec before the next transaction...")
            await asyncio.sleep(delay)
    _log("✅ All transactions processed.")

def get_collection_and_selfcalls_ahead(offset_seconds=2996):
    now = int(time.time())
    adjusted = now + offset_seconds
    return adjusted

def build_multicall_data(private_key, amount_in_wei, min_out=0, token_in=None, token_out=None):
    acct = Account.from_key(private_key)
    fee = 500
    recipient = acct.address
    sqrt_price_limit = 0
    calldata = encode_exact_input_single(
        token_in, token_out, fee, recipient, amount_in_wei, min_out, sqrt_price_limit
    )
    collection_and_selfcalls = get_collection_and_selfcalls_ahead(2996)
    multicall_args = abi_encode(["uint256", "bytes[]"], [collection_and_selfcalls, [calldata]])
    multicall_selector = bytes.fromhex("5ae401dc")
    tx_data = multicall_selector + multicall_args
    return tx_data

async def perform_swap_right(private_key, amount, min_out, token_in=WPHRS, token_out=USDC, proxy=None):
    loop = asyncio.get_running_loop()
    w3 = await loop.run_in_executor(None, get_w3, proxy)
    acct = Account.from_key(private_key)
    address = acct.address
    def _log(msg):
        log_wallet(address, msg)
    decimals = 18 if token_in == WPHRS else 6
    amount_in_wei = int(amount * (10 ** decimals))
    tx_data = build_multicall_data(private_key, amount_in_wei, min_out, token_in, token_out)
    nonce = await loop.run_in_executor(None, w3.eth.get_transaction_count, address)
    tx = {
        "from": address,
        "to": Web3.to_checksum_address(SWAP_CONTRACT_ADDRESS),
        "data": tx_data,
        "gas": 200000,
        "gasPrice": w3.to_wei(1, 'gwei'),
        "nonce": nonce,
        "value": 0,
        "chainId": 688688
    }
    signed = await loop.run_in_executor(None, w3.eth.account.sign_transaction, tx, private_key)
    try:
        tx_hash = await loop.run_in_executor(None, w3.eth.send_raw_transaction, signed.raw_transaction)
        _log(f"Transaction sent! Waiting for confirmation...")
        _log(f"TX hash: {w3.to_hex(tx_hash)}")
        receipt = await loop.run_in_executor(None, w3.eth.wait_for_transaction_receipt, tx_hash)
        if receipt.status == 1:
            _log(f"✅ Swap confirmed in block {receipt.blockNumber}")
        else:
            _log(f"❌ Swap failed!")
    except Exception as e:
        _log(f"❌ Error during swap: {e}")

async def run_bidirectional_swaps(private_key, amount, min_out, token_in=WPHRS, token_out=USDC, proxy=None):
    acct = Account.from_key(private_key)
    address = acct.address
    def _log(msg):
        log_wallet(address, msg)
    _log(f"▶️ Starting forward swap ({token_in} → {token_out}) x5")
    for i in range(5):
        if should_stop(address):
            _log(f"⏹️ Forward swap interrupted at step {i+1}")
            return
        _log(f"[{i+1}/10] Forward swap...")
        await perform_swap_right(private_key, amount, min_out, token_in, token_out, proxy=proxy)
        if should_stop(address):
            _log(f"⏹️ Stopped before waiting delay (forward)")
            return
        delay = random.randint(5, 15)
        _log(f"⏳ Waiting {delay} sec before next swap...")
        await asyncio.sleep(delay)
    _log(f"\n🔁 Starting reverse swap ({token_out} → {token_in}) x5")
    for i in range(5):
        if should_stop(address):
            _log(f"⏹️ Reverse swap interrupted at step {i+6}")
            return
        _log(f"[{i+6}/10] Reverse swap...")
        await perform_swap_right(private_key, amount, min_out, token_out, token_in, proxy=proxy)
        if i != 4:
            if should_stop(address):
                _log(f"⏹️ Stopped before waiting delay (reverse)")
                return
            delay = random.randint(5, 15)
            _log(f"⏳ Waiting {delay} sec before next swap...")
            await asyncio.sleep(delay)

async def check_balance_and_approve(private_key, token_address, amount, decimals, spender_address, proxy=None):
    loop = asyncio.get_running_loop()
    w3 = await loop.run_in_executor(None, get_w3, proxy)
    token_address = Web3.to_checksum_address(token_address)
    spender_address = Web3.to_checksum_address(spender_address)
    account = Account.from_key(private_key)
    address = account.address

    def _log(msg):
        log_wallet(address, msg)

    contract = w3.eth.contract(address=token_address, abi=erc20_abi)
    balance = await loop.run_in_executor(None, contract.functions.balanceOf(address).call)
    required = int(amount * (10 ** decimals))
    if balance < required:
        _log(f"[!] Insufficient balance: {balance / (10 ** decimals)} < {amount}")
        return False
    allowance = await loop.run_in_executor(None, contract.functions.allowance(address, spender_address).call)
    if allowance < required:
        _log(f"[~] Sending approve of {amount} tokens to {spender_address} ...")
        nonce = await loop.run_in_executor(None, w3.eth.get_transaction_count, address)
        tx = contract.functions.approve(spender_address, 2**256-1).build_transaction({
            'from': address,
            'nonce': nonce,
            'gas': 70000,
            'gasPrice': 0,
        })
        signed = await loop.run_in_executor(None, w3.eth.account.sign_transaction, tx, private_key)
        tx_hash = await loop.run_in_executor(None, w3.eth.send_raw_transaction, signed.raw_transaction)
        _log(f"[✓] Approve sent: {w3.to_hex(tx_hash)}")
        receipt = await loop.run_in_executor(None, w3.eth.wait_for_transaction_receipt, tx_hash)
        if receipt.status != 1:
            _log(f"[!] Approve failed!")
            return False
        await asyncio.sleep(2)
    else:
        _log(f"[✓] Approve already exists")
    return True

async def get_jwt(pk, address, force_refresh=False, proxy=None):
    jwt_path = f"jwt_{address}.txt"
    def _log(msg):
        log_wallet(address, msg)
    if os.path.exists(jwt_path) and not force_refresh:
        with open(jwt_path, "r") as f:
            jwt = f.read().strip()
            if jwt:
                _log(f"[+] JWT loaded from file for {address[:10]}...")
                return jwt
    message = encode_defunct(text="pharos")
    signed_message = Account.sign_message(message, pk)
    signature = signed_message.signature.hex()
    login_url = f"{PHAROS_API}/user/login?address={address}&signature={signature}&invite_code={INVITE_CODE}"
    headers = {
        "accept": "application/json, text/plain, */*",
        "user-agent": "Mozilla/5.0 (compatible)",
        "Referer": "https://testnet.pharosnetwork.xyz/",
    }
    proxy_url = normalize_proxy(proxy) if proxy else None
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.post(login_url, headers=headers, proxy=proxy_url) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    _log(f"[!] JWT login response not JSON for {address} (proxy={proxy_url})")
                    return None
        except Exception as e:
            _log(f"[!] Error while obtaining JWT for {address}: {e}")
            return None
    if data.get("code") == 0 and data.get("data", {}).get("jwt"):
        jwt = data["data"]["jwt"]
        with open(jwt_path, "w") as f:
            f.write(jwt)
        _log(f"[+] JWT for {address[:10]}... saved.")
        return jwt
    else:
        _log(f"[!] Failed to obtain JWT for {address}: {data}")
        return None

def get_random_eth_address():
    random_account = Account.create()
    return random_account.address

async def perform_check_in(private_key, proxy=None):
    proxy_url = normalize_proxy(proxy) if proxy else None
    timeout = aiohttp.ClientTimeout(total=30)
    acct = Account.from_key(private_key)
    address = acct.address

    def _log(msg):
        log_wallet(address, msg)
    message = encode_defunct(text="pharos")
    signed_message = Account.sign_message(message, private_key)
    signature = signed_message.signature.hex()
    login_url = f"https://api.pharosnetwork.xyz/user/login?address={address}&signature={signature}&invite_code=S6NGMzXSCDBxhnwo"
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.8",
        "authorization": "Bearer null",
        "sec-ch-ua": '"Chromium";v="136", "Brave";v="136", "Not.A/Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "sec-gpc": "1",
        "Referer": "https://testnet.pharosnetwork.xyz/",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "User-Agent": "Mozilla/5.0 (compatible)",
    }
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.post(login_url, headers=headers, proxy=proxy_url) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    _log(f"[!] Login response not JSON for {address} (proxy={proxy_url})")
                    return False
        except Exception as e:
            _log(f"[!] Login error for {address}: {e}")
            return False
        if data.get("code") != 0 or "jwt" not in data.get("data", {}):
            _log(f"[!] Login failed: {data}")
            return False
        jwt = data["data"]["jwt"]
        _log(f"[+] JWT obtained: {jwt[:16]}...")
        checkin_url = f"https://api.pharosnetwork.xyz/sign/in?address={address}"
        checkin_headers = dict(headers)
        checkin_headers["authorization"] = f"Bearer {jwt}"
        try:
            async with session.post(checkin_url, headers=checkin_headers, proxy=proxy_url) as resp:
                try:
                    checkin_data = await resp.json(content_type=None)
                except Exception:
                    _log(f"[!] Check-in response not JSON for {address}")
                    return False
        except Exception as e:
            _log(f"[!] Check-in error for {address}: {e}")
            return False
        if checkin_data.get("code") == 0:
            _log(f"[+] Check-in successful for {address}")
            return True
        else:
            _log(f"[!] Check-in failed: {checkin_data.get('msg')}")
            return False

async def approve_token(token_address, private_key, proxy=None):
    loop = asyncio.get_running_loop()
    w3_local = await loop.run_in_executor(None, get_w3, proxy)
    acct = Account.from_key(private_key)
    token_address = Web3.to_checksum_address(token_address)
    pm_address = Web3.to_checksum_address(POSITION_MANAGER)
    acct_address = Web3.to_checksum_address(acct.address)
    def _log(msg):
        log_wallet(acct_address, msg)
    token = w3_local.eth.contract(address=token_address, abi=erc20_abi)
    allowance = await loop.run_in_executor(None, token.functions.allowance(acct_address, pm_address).call)
    if allowance > 0:
        _log(f"ℹ️ Token {token_address} is already approved, skipping approve.")
        return
    nonce = await loop.run_in_executor(None, w3_local.eth.get_transaction_count, acct_address)
    tx = token.functions.approve(pm_address, 2 ** 256 - 1).build_transaction({
        "from": acct_address,
        "nonce": nonce,
        "gas": 60000,
        "gasPrice": w3_local.to_wei(1, 'gwei'),
        "chainId": 688688
    })
    signed = await loop.run_in_executor(None, w3_local.eth.account.sign_transaction, tx, private_key)
    tx_hash = await loop.run_in_executor(None, w3_local.eth.send_raw_transaction, signed.raw_transaction)
    _log(f"🟢 Approve TX sent: {w3_local.to_hex(tx_hash)}")
    await loop.run_in_executor(None, w3_local.eth.wait_for_transaction_receipt, tx_hash)

async def mint_liquidity(pk, proxy=None):
    loop = asyncio.get_running_loop()
    w3_local = await loop.run_in_executor(None, get_w3, proxy)
    acct = Account.from_key(pk)
    acct_address = Web3.to_checksum_address(acct.address)
    def _log(msg):
        log_wallet(acct_address, msg)
    position_manager = w3_local.eth.contract(
        address=Web3.to_checksum_address(POSITION_MANAGER),
        abi=POSITION_MANAGER_ABI
    )
    success_count = 0
    attempt = 0
    while success_count < 10:
        if should_stop(acct_address):
            log_wallet(acct_address, "⏹️ Liquidity minting stopped.")
            break
        attempt += 1
        _log(f"[{success_count + 1}/10] Adding liquidity (attempt {attempt})...")
        try:
            token0 = Web3.to_checksum_address(WPHRS)
            token1 = Web3.to_checksum_address(USDC)
            fee = 500
            amount0_desired = w3_local.to_wei(0.001, 'ether')
            amount1_desired = int(0.1115 * 10**6)
            deadline = int(time.time()) + 600
            tick_lower = -887220
            tick_upper = 887220
            nonce = await loop.run_in_executor(None, w3_local.eth.get_transaction_count, acct_address)
            tx = position_manager.functions.mint({
                "token0": token0,
                "token1": token1,
                "fee": fee,
                "tickLower": tick_lower,
                "tickUpper": tick_upper,
                "amount0Desired": amount0_desired,
                "amount1Desired": amount1_desired,
                "amount0Min": 0,
                "amount1Min": 0,
                "recipient": acct_address,
                "deadline": deadline
            }).build_transaction({
                "from": acct_address,
                "gas": 600000,
                "gasPrice": w3_local.to_wei(1, 'gwei'),
                "nonce": nonce,
                "chainId": 688688
            })
            signed = await loop.run_in_executor(None, w3_local.eth.account.sign_transaction, tx, pk)
            tx_hash = await loop.run_in_executor(None, w3_local.eth.send_raw_transaction, signed.raw_transaction)
            _log(f"Transaction sent! Waiting for confirmation...")
            receipt = await loop.run_in_executor(None, w3_local.eth.wait_for_transaction_receipt, tx_hash)
            if receipt.status == 1:
                _log(f"🎉 Liquidity added successfully! Block: {receipt.blockNumber}")
                success_count += 1
            else:
                _log(f"❌ Error while adding liquidity (tx failed).")
        except Exception as e:
            _log(f"[!] Error on attempt {attempt}: {e}")
            await asyncio.sleep(3)
            continue
        if success_count < 10:
            delay = random.randint(5, 15)
            _log(f"⏳ Waiting {delay} sec before the next attempt...")
            await asyncio.sleep(delay)

async def run_all_tasks(pk, address, proxy):
    jwt = await get_jwt(pk, address, False, proxy)
    if not jwt:
        return
    await check_daily_status(address, jwt, pk, proxy)
    await claim_faucet(pk, proxy)
    await send_10_txs(pk, proxy)
    amount = 0.001
    decimals = 18
    min_out = 0
    token_in = WPHRS
    token_out = USDC
    ok = await check_balance_and_approve(pk, token_in, amount, decimals, SWAP_CONTRACT_ADDRESS, proxy)
    if ok:
        await run_bidirectional_swaps(pk, amount, min_out, token_in, token_out, proxy=proxy)
    await approve_token(Web3.to_checksum_address(WPHRS), pk, proxy)
    await approve_token(Web3.to_checksum_address(USDC), pk, proxy)
    await mint_liquidity(pk, proxy)

async def check_daily_status(address, jwt, private_key=None, proxy=None):
    def _log(msg):
        log_wallet(address, msg)
    url = f"{PHAROS_API}/faucet/status?address={address}"
    headers = {
        "accept": "application/json, text/plain, */*",
        "user-agent": "Mozilla/5.0 (compatible)",
        "authorization": f"Bearer {jwt}",
        "Referer": "https://testnet.pharosnetwork.xyz/",
    }
    proxy_url = normalize_proxy(proxy) if proxy else None
    timeout = aiohttp.ClientTimeout(total=20)
    data = None
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.get(url, headers=headers, proxy=proxy_url) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception as e:
                    text = await resp.text()
                    _log(f"[!] Error parsing JSON for status {address}: {e} (Raw: {text})")
                    return
        except Exception as e:
            _log(f"[!] Error fetching faucet status: {e}")
            return
    _log(f"=== Check-in status for {address} ===")
    if not isinstance(data, dict):
        _log(f"[!] No or bad data received for check-in status! data={data}")
        return
    if data.get("code") == 0 and data.get("data"):
        d = data["data"]
        if d.get("is_able_to_faucet"):
            _log("✅ You can check-in right now!")
            if private_key is not None:
                success = await perform_check_in(private_key, proxy=proxy)
                if success:
                    _log("✅ Check-in successful!")
                else:
                    _log("❌ Failed to check-in.")
        else:
            ts = d.get("avaliable_timestamp")
            if ts:
                next_time = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                _log(f"✅ Already checked in. Next check-in will be available at: {next_time}")
            else:
                _log("✅ Already checked in. (No timestamp available)")
    else:
        _log(f"[!] Error checking status: {data}")


async def run_wallet(pk, proxy):
    acct = Account.from_key(pk)
    address = acct.address
    log_wallet(address, f"▶️ Wallet runner started with proxy {proxy}")
    while True:
        status = WALLET_STATUS.get(address)
        if not isinstance(status, dict):
            log_wallet(address, f"[DEBUG] WALLET_STATUS[{address}] is not dict: {repr(status)} — setting to idle")
            set_wallet_status(address, "idle")
            await asyncio.sleep(1)
            continue
        if status.get("status") == "global_looping" and GLOBAL_LOOP_EVENT.is_set():
            log_wallet(address, "[DEBUG] === GLOBAL LOOP BRANCH ===")
            set_wallet_status(address, "global_looping", status.get("task", "all"))
            while (
                WALLET_STATUS.get(address, {}).get("status") == "global_looping"
                and GLOBAL_LOOP_EVENT.is_set()):
                task = WALLET_STATUS.get(address, {}).get("task", "all")
                log_wallet(address, f"[DEBUG] GLOBAL_LOOP: task={task}")
                try:
                    await handle_task(pk, address, proxy, task)
                except Exception as e:
                    log_wallet(address, f"❌ [GLOBAL LOOP] Error: {e}")
                if (
                    should_stop(address)
                    or WALLET_STATUS.get(address, {}).get("status") != "global_looping"
                    or not GLOBAL_LOOP_EVENT.is_set()
                ):
                    set_wallet_status(address, "idle")
                    break
                with config_lock:
                    interval_minutes = GLOBAL_CONFIG.get("loop_interval", 60)
                delay = interval_minutes * 60
                log_wallet(address, f"[DEBUG] GLOBAL_LOOP: sleep for {delay} seconds (interval param: {interval_minutes})")
                for _ in range(delay):
                    if (
                        should_stop(address)
                        or WALLET_STATUS.get(address, {}).get("status") != "global_looping"
                        or not GLOBAL_LOOP_EVENT.is_set()):
                        break
                    await asyncio.sleep(1)
            continue

        elif status.get("status") == "looping":
            interval = LOOP_INTERVALS.get(address, 60)
            set_wallet_status(address, "looping", status.get("task", "all"))
            while WALLET_STATUS.get(address, {}).get("status") == "looping":
                task = status.get("task", "all")
                log_wallet(address, f"[DEBUG] LOOP: task={task}")
                try:
                    await handle_task(pk, address, proxy, task)
                except Exception as e:
                    log_wallet(address, f"❌ [LOOP] Error: {e}")
                if should_stop(address) or WALLET_STATUS.get(address, {}).get("status") != "looping":
                    set_wallet_status(address, "idle")
                    break
                delay = interval * 60
                for _ in range(delay):
                    if should_stop(address) or WALLET_STATUS.get(address, {}).get("status") != "looping":
                        break
                    await asyncio.sleep(1)
            continue

        elif status.get("status") == "running":
            if should_stop(address):
                log_wallet(address, f"⏹️ Task was stopped.")
                set_wallet_status(address, "idle")
                continue
            task = status.get("task", "all")
            set_wallet_status(address, "running", task)
            try:
                await handle_task(pk, address, proxy, task)
            except Exception as e:
                log_wallet(address, f"❌ Error during task {task}: {e}")
            set_wallet_status(address, "idle")
            await asyncio.sleep(2)
            continue
        await asyncio.sleep(1)
        continue

async def handle_task(pk, address, proxy, task):
    if task == "check_in":
        jwt = await get_jwt(pk, address, False, proxy)
        if jwt:
            await check_daily_status(address, jwt, pk, proxy)
    elif task == "claim_faucet":
        await claim_faucet(pk, proxy)
    elif task == "send_txs":
        await send_10_txs(pk, proxy)
    elif task == "perform_swaps":
        amount = 0.001
        min_out = 0
        amount_wphrs = amount
        amount_usdc = 1
        ok1 = await check_balance_and_approve(pk, WPHRS, amount_wphrs, 18, SWAP_CONTRACT_ADDRESS, proxy)
        ok2 = await check_balance_and_approve(pk, USDC, amount_usdc, 6, SWAP_CONTRACT_ADDRESS, proxy)
        if ok1 and ok2:
            await run_bidirectional_swaps(pk, amount, min_out, WPHRS, USDC, proxy)
        else:
            log_wallet(address, "⚠️ Skipped swaps due to missing approvals.")
    elif task == "add_liquidity":
        await approve_token(WPHRS, pk, proxy)
        await approve_token(USDC, pk, proxy)
        await mint_liquidity(pk, proxy)
    elif task == "all":
        await run_all_tasks(pk, address, proxy)

async def main():
    private_keys = load_private_keys()
    proxies = load_proxies()
    if not private_keys:
        print("[!] No private keys found.")
        return
    if not proxies:
        print("[!] No proxies found, all wallets will run without proxy.")
        proxies = [None] * len(private_keys)
    elif len(proxies) < len(private_keys):
        print("[!] Number of proxies is less than private keys — reusing proxies.")
        proxies *= (len(private_keys) // len(proxies)) + 1
    tasks = []
    for i, pk in enumerate(private_keys):
        proxy = proxies[i]
        tasks.append(asyncio.create_task(run_wallet(pk, proxy)))
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())