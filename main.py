import json
import os
import requests
from eth_account import Account
from eth_account.messages import encode_defunct
from datetime import datetime
from web3 import Web3
import random
import time
from eth_abi import encode as abi_encode
from colorama import init, Fore, Style

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


PHAROS_RPC = "https://testnet.dplabs-internal.com"
PHAROS_API = "https://api.pharosnetwork.xyz"
INVITE_CODE = "g4oanA8cB1e82QD1"
KEYS_PATH = "private_keys.txt"
w3 = Web3(Web3.HTTPProvider(PHAROS_RPC))
SWAP_CONTRACT_ADDRESS = "0x1a4de519154ae51200b0ad7c90f7fac75547888a"
POSITION_MANAGER = Web3.to_checksum_address("0xf8a1d4ff0f9b9af7ce58e1fc1833688f3bfd6115")
WPHRS = "0x76aaada469d23216be5f7c596fa25f282ff9b364"
USDC = "0xad902cf99c2de2f1ba5ec4d642fd7e49cae9ee37"

ERC20_ABI = ("""
[
  {"constant":false,"inputs":[{"name":"spender","type":"address"},{"name":"value","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"type":"function"},
  {"constant":true,"inputs":[{"name":"owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"},
  {"constant":true,"inputs":[{"name":"owner","type":"address"},{"name":"spender","type":"address"}],"name":"allowance","outputs":[{"name":"remaining","type":"uint256"}],"type":"function"}
]
""")

SWAP_ROUTER_ABI = json.loads("""
[
  {
    "inputs": [
      {
        "components": [
          {"internalType": "address", "name": "tokenIn", "type": "address"},
          {"internalType": "address", "name": "tokenOut", "type": "address"},
          {"internalType": "uint24", "name": "fee", "type": "uint24"},
          {"internalType": "address", "name": "recipient", "type": "address"},
          {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
          {"internalType": "uint256", "name": "amountOutMinimum", "type": "uint256"},
          {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"}
        ],
        "internalType": "struct IV3SwapRouter.ExactInputSingleParams",
        "name": "params",
        "type": "tuple"
      }
    ],
    "name": "exactInputSingle",
    "outputs": [
      {"internalType": "uint256", "name": "amountOut", "type": "uint256"}
    ],
    "stateMutability": "payable",
    "type": "function"
  },
  {
    "inputs": [
      {"internalType": "bytes[]", "name": "data", "type": "bytes[]"}
    ],
    "name": "multicall",
    "outputs": [
      {"internalType": "bytes[]", "name": "results", "type": "bytes[]"}
    ],
    "stateMutability": "payable",
    "type": "function"
  }
]
""")

CONTRACT_ABI = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "collectionAndSelfcalls", "type": "uint256"},
            {"internalType": "bytes[]", "name": "data", "type": "bytes[]"}
        ],
        "name": "multicall",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

position_manager_abi = [
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "token0", "type": "address"},
                    {"internalType": "address", "name": "token1", "type": "address"},
                    {"internalType": "uint24", "name": "fee", "type": "uint24"},
                    {"internalType": "int24", "name": "tickLower", "type": "int24"},
                    {"internalType": "int24", "name": "tickUpper", "type": "int24"},
                    {"internalType": "uint256", "name": "amount0Desired", "type": "uint256"},
                    {"internalType": "uint256", "name": "amount1Desired", "type": "uint256"},
                    {"internalType": "uint256", "name": "amount0Min", "type": "uint256"},
                    {"internalType": "uint256", "name": "amount1Min", "type": "uint256"},
                    {"internalType": "address", "name": "recipient", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"}
                ],
                "internalType": "struct INonfungiblePositionManager.MintParams",
                "name": "params",
                "type": "tuple"
            }
        ],
        "name": "mint",
        "outputs": [
            {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"internalType": "uint128", "name": "liquidity", "type": "uint128"},
            {"internalType": "uint256", "name": "amount0", "type": "uint256"},
            {"internalType": "uint256", "name": "amount1", "type": "uint256"}
        ],
        "stateMutability": "payable",
        "type": "function"
    }
]

erc20_abi = json.loads(ERC20_ABI)
def load_proxies(filename="proxies.txt"):
    try:
        with open(filename, "r") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print("[!] File proxies.txt not found — launching without proxy")
        return []

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

def claim_faucet(pk, proxy=None):
    acct = Account.from_key(pk)
    address = acct.address
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
    proxies = {"http": proxy, "https": proxy} if proxy else None
    try:
        login_resp = requests.post(login_url, headers=headers, proxies=proxies)
        login_data = login_resp.json()
        if login_data.get("code") != 0 or "jwt" not in login_data.get("data", {}):
            print(f"[!] Login failed: {login_data}")
            return
        jwt = login_data["data"]["jwt"]
        print(f"[+] JWT received: {jwt[:16]}...")
        faucet_headers = dict(headers)
        faucet_headers["authorization"] = f"Bearer {jwt}"
        status_resp = requests.get(
            f"{PHAROS_API}/faucet/status?address={address}",
            headers=faucet_headers,
            proxies=proxies
        )
        status_data = status_resp.json()
        if status_data.get("data", {}).get("is_able_to_faucet"):
            claim_resp = requests.post(
                f"{PHAROS_API}/faucet/daily?address={address}",
                headers=faucet_headers,
                proxies=proxies
            )
            claim_data = claim_resp.json()
            if claim_resp.status_code == 200 and claim_data.get("code") == 0:
                print(f"✅ Faucet successfully claimed for {address}")
            else:
                print(f"❌ Error claiming faucet: {claim_data}")
        else:
            next_ts = status_data.get("data", {}).get("avaliable_timestamp")
            if next_ts:
                readable = datetime.fromtimestamp(next_ts).strftime('%Y-%m-%d %H:%M:%S')
                print(f"🕐 Faucet will be available at: {readable}")
            else:
                print("🚫 Faucet is not available")
    except Exception as e:
        print(f"❌ Error while requesting faucet: {e}")

def send_10_txs(private_key, proxy=None):
    from web3 import HTTPProvider
    import requests
    if proxy:
        session = requests.Session()
        session.proxies = {
            'http': proxy,
            'https': proxy
        }
        provider = HTTPProvider(PHAROS_RPC, session=session)
        w3 = Web3(provider)
    else:
        w3 = Web3(Web3.HTTPProvider(PHAROS_RPC))
    acct = Account.from_key(private_key)
    address = acct.address
    print(f"\n{Colors.cyan}▶️ Sending 10 transactions from address: {Colors.bold}{address}{Colors.reset}")
    nonce = w3.eth.get_transaction_count(address)
    for i in range(10):
        to_address = get_random_eth_address()
        value = w3.to_wei(random.uniform(0.00001, 0.0001), 'ether')
        tx = {
            'nonce': nonce + i,
            'to': to_address,
            'value': value,
            'gas': 21000,
            'gasPrice': 0,  # Pharos testnet
            'chainId': 688688,
        }
        signed_tx = w3.eth.account.sign_transaction(tx, private_key)
        try:
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            print(f"{Colors.beige}[{i + 1}/10] TX sent → {to_address}{Colors.reset}")
            print(f"{Colors.blue}⏳ Waiting for confirmation...{Colors.reset}")
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            if receipt.status == 1:
                print(f"{Colors.green}✅ Confirmed in block {receipt.blockNumber}: {w3.to_hex(tx_hash)}{Colors.reset}")
            else:
                print(f"{Colors.red}❌ Transaction failed! {w3.to_hex(tx_hash)}{Colors.reset}")
        except Exception as e:
            print(f"{Colors.red}[{i + 1}/10] ❌ Error while sending: {e}{Colors.reset}")
        if i != 9:
            delay = random.randint(5, 15)
            print(f"{Colors.yellow}⏳ Waiting {delay} sec before the next transaction...{Colors.reset}")
            time.sleep(delay)
    print(f"{Colors.green}✅ All transactions processed.{Colors.reset}")

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

def perform_swap_right(private_key, amount, min_out, token_in=WPHRS, token_out=USDC, proxy=None):
    if proxy:
        session = requests.Session()
        session.proxies = {"http": proxy, "https": proxy}
        provider = Web3.HTTPProvider(PHAROS_RPC, session=session)
        w3 = Web3(provider)
    else:
        w3 = Web3(Web3.HTTPProvider(PHAROS_RPC))
    acct = Account.from_key(private_key)
    address = acct.address
    decimals = 18 if token_in == WPHRS else 6
    amount_in_wei = int(amount * (10 ** decimals))
    tx_data = build_multicall_data(private_key, amount_in_wei, min_out, token_in, token_out)
    nonce = w3.eth.get_transaction_count(address)
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
    signed = w3.eth.account.sign_transaction(tx, private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"{Colors.beige}Транзакция отправлена! Ожидаем подтверждения...{Colors.reset}")
    print(f"{Colors.blue}{w3.to_hex(tx_hash)}{Colors.reset}")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status == 1:
        print(f"{Colors.green}✅ Swap confirmed in block {receipt.blockNumber}{Colors.reset}")
    else:
        print(f"{Colors.red}❌ Swap failed!{Colors.reset}")


def run_bidirectional_swaps(private_key, amount, min_out, token_in=WPHRS, token_out=USDC, proxy=None):
    print(f"{Colors.cyan}▶️ Starting forward swap ({token_in} → {token_out}) x5{Colors.reset}")
    for i in range(5):
        print(f"{Colors.bold}[{i+1}/10] Forward swap...{Colors.reset}")
        perform_swap_right(private_key, amount, min_out, token_in, token_out, proxy=proxy)
        delay = random.randint(5, 15)
        print(f"{Colors.yellow}⏳ Waiting {delay} sec before next swap...{Colors.reset}")
        time.sleep(delay)
    print(f"\n{Colors.cyan}🔁 Starting reverse swap ({token_out} → {token_in}) x5{Colors.reset}")
    for i in range(5):
        print(f"{Colors.bold}[{i+6}/10] Reverse swap...{Colors.reset}")
        perform_swap_right(private_key, amount, min_out, token_out, token_in, proxy=proxy)
        if i != 4:
            delay = random.randint(5, 15)
            print(f"{Colors.yellow}⏳ Waiting {delay} sec before next swap...{Colors.reset}")
            time.sleep(delay)

def check_balance_and_approve(private_key, token_address, amount, decimals, spender_address, proxy=None):
    from web3 import HTTPProvider
    import requests
    if proxy:
        session = requests.Session()
        session.proxies = {"http": proxy, "https": proxy}
        provider = HTTPProvider(PHAROS_RPC, session=session)
        w3 = Web3(provider)
    else:
        w3 = Web3(Web3.HTTPProvider(PHAROS_RPC))
    token_address = Web3.to_checksum_address(token_address)
    spender_address = Web3.to_checksum_address(spender_address)
    account = Account.from_key(private_key)
    address = account.address
    contract = w3.eth.contract(address=token_address, abi=erc20_abi)
    balance = contract.functions.balanceOf(address).call()
    required = int(amount * (10 ** decimals))
    if balance < required:
        print(f"[!] Insufficient balance: {balance / (10 ** decimals)} < {amount}")
        return False
    allowance = contract.functions.allowance(address, spender_address).call()
    if allowance < required:
        print(f"[~] Sending approve of {amount} tokens to {spender_address} ...")
        nonce = w3.eth.get_transaction_count(address)
        tx = contract.functions.approve(spender_address, 2**256-1).build_transaction({
            'from': address,
            'nonce': nonce,
            'gas': 70000,
            'gasPrice': 0,
        })
        signed = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        print(f"[✓] Approve sent: {w3.to_hex(tx_hash)}")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status != 1:
            print(f"[!] Approve failed!")
            return False
        time.sleep(2)
    else:
        print(f"[✓] Approve already exists")
    return True

def get_jwt(api, address, force_refresh=False, proxy=None):
    jwt_path = f"jwt_{address}.txt"
    if os.path.exists(jwt_path) and not force_refresh:
        with open(jwt_path, "r") as f:
            jwt = f.read().strip()
            if jwt:
                return jwt
    message = encode_defunct(text="pharos")
    signed_message = Account.sign_message(message, api)
    signature = signed_message.signature.hex()
    login_url = f"{PHAROS_API}/user/login?address={address}&signature={signature}&invite_code={INVITE_CODE}"
    headers = {
        "accept": "application/json, text/plain, */*",
        "user-agent": "Mozilla/5.0 (compatible)",
        "Referer": "https://testnet.pharosnetwork.xyz/",
    }
    proxies = {"http": proxy, "https": proxy} if proxy else None
    try:
        resp = requests.post(login_url, headers=headers, proxies=proxies, timeout=20)
        data = resp.json()
    except Exception as e:
        print(f"[!] Error while obtaining JWT: {e}")
        return None
    if data.get("code") == 0 and data.get("data", {}).get("jwt"):
        jwt = data["data"]["jwt"]
        with open(jwt_path, "w") as f:
            f.write(jwt)
        print(f"[+] JWT for {address[:10]}... saved.")
        return jwt
    else:
        print(f"[!] Failed to obtain JWT for {address}: {data}")
        return None

def get_random_eth_address():
    random_account = Account.create()
    return random_account.address

def perform_check_in(private_key, proxy=None):
    acct = Account.from_key(private_key)
    address = acct.address
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
    proxies = {"http": proxy, "https": proxy} if proxy else None
    try:
        resp = requests.post(login_url, headers=headers, proxies=proxies, timeout=20)
        data = resp.json()
    except Exception as e:
        print(f"[!] Login error: {e}")
        return False
    if data.get("code") != 0 or "jwt" not in data.get("data", {}):
        print(f"[!] Login failed: {data}")
        return False
    jwt = data["data"]["jwt"]
    print(f"[+] JWT obtained: {jwt[:16]}...")
    checkin_url = f"https://api.pharosnetwork.xyz/sign/in?address={address}"
    checkin_headers = dict(headers)
    checkin_headers["authorization"] = f"Bearer {jwt}"
    try:
        resp = requests.post(checkin_url, headers=checkin_headers, proxies=proxies, timeout=20)
        checkin_data = resp.json()
    except Exception as e:
        print(f"[!] Check-in error: {e}")
        return False
    if checkin_data.get("code") == 0:
        print(f"[+] Check-in successful for {address}")
        return True
    else:
        print(f"[!] Check-in failed: {checkin_data.get('msg')}")
        return False

def approve_token(token_address, private_key, proxy=None):
    import requests
    from web3 import HTTPProvider
    acct = Account.from_key(private_key)
    if proxy:
        session = requests.Session()
        session.proxies = {"http": proxy, "https": proxy}
        w3_local = Web3(HTTPProvider(PHAROS_RPC, session=session))
    else:
        w3_local = Web3(Web3.HTTPProvider(PHAROS_RPC))
    token = w3_local.eth.contract(address=token_address, abi=erc20_abi)
    allowance = token.functions.allowance(acct.address, POSITION_MANAGER).call()
    if allowance > 0:
        print(f"{Colors.blue}ℹ️ Token {token_address} is already approved, skipping approve.{Colors.reset}")
        return
    tx = token.functions.approve(POSITION_MANAGER, 2 ** 256 - 1).build_transaction({
        "from": acct.address,
        "nonce": w3_local.eth.get_transaction_count(acct.address),
        "gas": 60000,
        "gasPrice": w3_local.to_wei(1, 'gwei'),
        "chainId": 688688
    })
    signed = w3_local.eth.account.sign_transaction(tx, private_key)
    tx_hash = w3_local.eth.send_raw_transaction(signed.raw_transaction)
    print(f"{Colors.green}🟢 Approve TX sent: {w3_local.to_hex(tx_hash)}{Colors.reset}")
    w3_local.eth.wait_for_transaction_receipt(tx_hash)

def mint_liquidity(pk, proxy=None):
    import requests
    from web3 import HTTPProvider
    acct = Account.from_key(pk)
    if proxy:
        session = requests.Session()
        session.proxies = {"http": proxy, "https": proxy}
        w3_local = Web3(HTTPProvider(PHAROS_RPC, session=session))
    else:
        w3_local = Web3(Web3.HTTPProvider(PHAROS_RPC))
    position_manager = w3_local.eth.contract(address=POSITION_MANAGER, abi=position_manager_abi)
    for i in range(10):
        print(f"{Colors.cyan}[{i+1}/10] Adding liquidity...{Colors.reset}")
        try:
            token0 = Web3.to_checksum_address(WPHRS)
            token1 = Web3.to_checksum_address(USDC)
            fee = 500
            amount0_desired = w3_local.to_wei(0.001, 'ether')
            amount1_desired = int(0.1115 * 10**6)
            deadline = int(time.time()) + 600
            tick_lower = -887220
            tick_upper = 887220
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
                "recipient": acct.address,
                "deadline": deadline
            }).build_transaction({
                "from": acct.address,
                "gas": 600000,
                "gasPrice": w3_local.to_wei(1, 'gwei'),
                "nonce": w3_local.eth.get_transaction_count(acct.address),
                "chainId": 688688
            })
            signed = w3_local.eth.account.sign_transaction(tx, pk)
            tx_hash = w3_local.eth.send_raw_transaction(signed.raw_transaction)
            print(f"{Colors.beige}✅ Transaction sent: {w3_local.to_hex(tx_hash)}{Colors.reset}")
            receipt = w3_local.eth.wait_for_transaction_receipt(tx_hash)
            if receipt.status == 1:
                print(f"{Colors.green}🎉 Liquidity added successfully! Block: {receipt.blockNumber}{Colors.reset}")
            else:
                print(f"{Colors.red}❌ Error while adding liquidity.{Colors.reset}")
        except Exception as e:
            print(f"{Colors.red}[!] Error on attempt {i+1}: {e}{Colors.reset}")
            continue
        if i != 9:
            delay = random.randint(5, 15)
            print(f"{Colors.yellow}⏳ Waiting {delay} sec before the next attempt...{Colors.reset}")
            time.sleep(delay)


def show_menu():
    print("\nWhat would you like to do?")
    print("1. Perform check-in")
    print("2. Claim tokens from faucet")
    print("3. Send 10 transactions")
    print("4. Perform 10 swaps")
    print("5. Perform 10 liquidity adds (staking)")
    print("6. Do everything (sequentially)")
    print("7. Loop everything endlessly\n")
    while True:
        choice = input("Enter the action number and press Enter: ")
        if choice in {'1', '2', '3', '4', '5', '6', '7'}:
            return int(choice)
        print("Invalid input. Please try again.")

def run_all_tasks(pk, address, proxy):
    jwt = get_jwt(pk, address, False, proxy)
    if not jwt:
        return
    check_daily_status(address, jwt, pk, proxy)
    claim_faucet(pk, proxy)
    send_10_txs(pk, proxy)
    amount = 0.001
    decimals = 18
    min_out = 0
    token_in = WPHRS
    token_out = USDC
    ok = check_balance_and_approve(pk, token_in, amount, decimals, SWAP_CONTRACT_ADDRESS, proxy)
    if ok:
        run_bidirectional_swaps(pk, amount, min_out, token_in, token_out, proxy=proxy)
    approve_token(Web3.to_checksum_address(WPHRS), pk, proxy)
    approve_token(Web3.to_checksum_address(USDC), pk, proxy)
    mint_liquidity(pk, proxy)

def check_daily_status(address, jwt, private_key=None, proxy=None):
    url = f"{PHAROS_API}/faucet/status?address={address}"
    headers = {
        "accept": "application/json, text/plain, */*",
        "user-agent": "Mozilla/5.0 (compatible)",
        "authorization": f"Bearer {jwt}",
        "Referer": "https://testnet.pharosnetwork.xyz/",
    }
    proxies = {"http": proxy, "https": proxy} if proxy else None
    try:
        resp = requests.get(url, headers=headers, proxies=proxies, timeout=15)
        data = resp.json()
    except Exception as e:
        print(f"[!] Error fetching faucet status: {e}")
        return
    print(f"\n=== Check-in status for {address} ===")
    if data.get("code") == 0 and data.get("data"):
        d = data["data"]
        if d["is_able_to_faucet"]:
            print("✅ You can check-in right now!")
            if private_key is not None:
                success = perform_check_in(private_key, proxy=proxy)
                if success:
                    print("✅ Check-in successful!")
                else:
                    print("❌ Failed to check-in.")
        else:
            ts = d["avaliable_timestamp"]
            next_time = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
            print(f"✅ Already checked in.\nNext check-in will be available at: {next_time}")
    else:
        print(f"[!] Error checking status: {data}")

def load_private_keys():
    if not os.path.exists(KEYS_PATH):
        print(f"[!] File {KEYS_PATH} not found!")
        return []
    with open(KEYS_PATH, "r") as f:
        keys = [line.strip() for line in f if line.strip()]
    return keys


if __name__ == "__main__":
    private_keys = load_private_keys()
    proxies = load_proxies()
    if not private_keys:
        print("[!] No private keys found.")
        exit(1)
    if not proxies:
        print("[!] No proxies found, all wallets will run without proxy.")
        proxies = [None] * len(private_keys)
    elif len(proxies) < len(private_keys):
        print("[!] Number of proxies is less than number of private keys. Proxies will be reused.")
        proxies *= (len(private_keys) // len(proxies)) + 1

    choice = show_menu()

    for i, pk in enumerate(private_keys):
        proxy = proxies[i]
        try:
            acct = Account.from_key(pk)
            address = acct.address
            print(f"\n[~] Using wallet: {address} with proxy: {proxy}")
            jwt = get_jwt(pk, address, False, proxy)
            if not jwt:
                continue

            if choice == 1:
                check_daily_status(address, jwt, pk, proxy)
            elif choice == 2:
                claim_faucet(pk, proxy)
            elif choice == 3:
                send_10_txs(pk, proxy)
            elif choice == 4:
                amount = 0.001
                decimals = 18
                min_out = 0
                token_in = WPHRS
                token_out = USDC
                ok = check_balance_and_approve(pk, token_in, amount, decimals, SWAP_CONTRACT_ADDRESS, proxy)
                if ok:
                    run_bidirectional_swaps(pk, amount, min_out, token_in, token_out, proxy=proxy)
                else:
                    print(f"{Colors.red}[!] Swap skipped due to insufficient wPHRS balance or no approval.{Colors.reset}")
            elif choice == 5:
                approve_token(Web3.to_checksum_address(WPHRS), pk, proxy)
                approve_token(Web3.to_checksum_address(USDC), pk, proxy)
                mint_liquidity(pk, proxy)
            elif choice == 6:
                run_all_tasks(pk, address, proxy)
            if choice == 7:
                interval_min = input("Enter interval between runs in minutes: ").strip()
                try:
                    interval_min = int(interval_min)
                    if interval_min <= 0:
                        raise ValueError
                except ValueError:
                    print("[!] Invalid input. Using default value: 60 minutes.")
                    interval_min = 60
                print(f"\n🔁 Starting infinite loop with interval {interval_min} minutes.\nPress Ctrl+C to stop.\n")
                while True:
                    for i, pk in enumerate(private_keys):
                        proxy = proxies[i]
                        try:
                            acct = Account.from_key(pk)
                            address = acct.address
                            print(f"\n[~] Using wallet: {address} with proxy: {proxy}")
                            run_all_tasks(pk, address, proxy)
                        except Exception as e:
                            print(f"[!] Error on wallet {pk[:10]}...: {e}")
                    print(f"\n⏳ Waiting {interval_min} minutes before next cycle...\n")
                    time.sleep(interval_min * 60)
        except Exception as e:
            print(f"[!] Error on wallet {pk[:10]}...: {e}")