# Pharos-autobot
autoswap, auto send transactions, auto add liquidity, auto checkin, auto faucet, fully autonomus
autoswap, auto send transactions, auto add liquidity, auto checkin, auto faucet, fully autonomus

🚀 Pharos Testnet Farming Bot This is a powerful and fully automated Python bot for interacting with the Pharos Testnet. It helps you seamlessly perform all necessary daily testnet activities and is perfect for maximizing your on-chain presence.

✨ Features

✅ Daily Check-in automation

✅ Claim faucet tokens automatically

✅ Send 10 random transactions to boost activity

✅ Perform 10 swaps (5 forward + 5 reverse)

✅ Approve tokens for contracts if needed

✅ Add liquidity via NFT positions (Uniswap V3 style)

✅ Full colorized console output with colorama

✅ Built-in proxy support for multi-wallet setups

✅ Interactive CLI menu

🔁 Optional infinite loop mode for farming on autopilot

🛠 Installation

Clone the repo
git clone https://github.com/yourusername/pharos-testnet-bot.git

cd pharos-testnet-bot

Install dependencies
pip install -r requirements.txt

If you're using proxies or running multiple wallets, Python 3.11+ is recommended.

⚙️ Setup

Add your private keys Create a file named private_keys.txt and put one private key per line.
0xabc123...

0xdef456...

(Optional) Add proxies Create a proxies.txt file if you want to route requests through proxies:
http://user1:pass1@proxy1.com:port

http://user2:pass2@proxy2.com:port

http://proxy3.com:port

▶️ Usage Run the script:

python main.py

You'll see an interactive menu:

What would you like to do?

Perform check-in
Claim tokens from faucet
Send 10 transactions
Perform 10 swaps
Perform 10 liquidity adds (staking)
Do everything (sequentially)
Loop everything endlessly Choose an action (1–7) and let the bot handle the rest 🎯
If you select option 7, you'll be asked to provide an interval between cycles in minutes — the bot will then run indefinitely.

🔒 Disclaimer This tool is provided for educational and testing purposes only. Make sure you never reuse mainnet keys, and understand the risks of using automated scripts.

📬 Contributions Feel free to open an issue, suggest improvements, or submit a pull request!

Let me know if you want a logo/banner, pip packaging, or Dockerfile to go along with it!
