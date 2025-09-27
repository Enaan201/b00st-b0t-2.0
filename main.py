# main.py (fixed)
import os
import json
import logging
import traceback
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

# third-party libs
import tls_client
import requests
import httpx
import yaml
import base64
import random

# local modules
from logger import *
from fingerprints import fps

from flask import Flask, request, jsonify, Response

# --- Flask app (single creation) ---
app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Load config (if present)
config = {}
try:
    with open('config.yml', 'r') as c:
        config = yaml.safe_load(c) or {}
        logging.info("Loaded config.yml")
except FileNotFoundError:
    logging.warning("config.yml not found; continuing with defaults")
except Exception:
    logging.exception("Failed to load config.yml; continuing with defaults")


# --- Helper utilities ---
def encode_to_base64(json_object):
    json_str = json.dumps(json_object)
    json_bytes = json_str.encode("utf-8")
    base64_bytes = base64.b64encode(json_bytes)
    return base64_bytes.decode("utf-8")


def get_cookies() -> dict:
    try:
        response = requests.get("https://discord.com").cookies
        return {
            "__dcfduid": response.get("__dcfduid"),
            "__sdcfduid": response.get("__sdcfduid"),
            "_cfuvid": response.get("_cfuvid"),
            "__cfruid": response.get("__cfruid"),
        }
    except Exception:
        return {}


def ran_str():
    return "".join(
        random.choice("9830da1a6f376cc753f0fbc28d1ffbbe")
        for _ in range(len("9830da1a6f376cc753f0fbc28d1ffbbe"))
    )


def get_fingerprint():
    try:
        resp = httpx.get("https://discord.com/api/v10/experiments", timeout=10.0)
        return resp.json().get("fingerprint")
    except Exception:
        logging.exception("Error fetching fingerprint; retrying")
        return get_fingerprint()


class BTool:
    def __init__(self, token, invite):
        self.chrome = "126"
        fingerprint_dict = random.choice(fps)
        self.user_agent = fingerprint_dict.get("user-agent")
        self.x_super_properties = fingerprint_dict.get("x-super-properties")
        self.session = tls_client.Session(
            client_identifier="chrome_" + self.chrome, random_tls_extension_order=True
        )
        if config.get("UseProxy"):
            self.session.proxies = {
                'https': 'http://' + config.get("Proxy"),
                'http': 'http://' + config.get("Proxy")
            }
        else:
            self.session.proxies = None

        self.full_token = token
        self.token = token.split(":")[2] if "@" in token else token
        log("INFO", f"Using [{self.token[:23]}***-***]")
        self.headers = {
            "authorization": self.token,
            "user-agent": self.user_agent,
            "x-super-properties": self.x_super_properties,
        }
        self.join_data = {"session_id": ran_str()}
        self.guild = None
        self.invite = invite

    def join_guild(self) -> bool:
        try:
            r = self.session.post(
                f"https://discord.com/api/v9/invites/{self.invite}",
                headers=self.headers,
                json=self.join_data,
                cookies=get_cookies(),
            )
            if r.status_code == 200:
                log("DBG", f"Joined Guild: {self.invite}")
                self.guild = r.json().get("guild", {}).get("id")
                return True
            else:
                log("ERR", f"Failed To Join Guild: {r.text}")
                return False
        except Exception:
            logging.exception("Exception in join_guild")
            return False

    def put_boost(self) -> bool:
        if getattr(self, "guild", None):
            try:
                boost_dat = self.session.get(
                    "https://discord.com/api/v9/users/@me/guilds/premium/subscription-slots",
                    headers=self.headers,
                    cookies=get_cookies(),
                )
                if boost_dat.status_code == 200:
                    for boost in boost_dat.json():
                        boost_id = boost.get("id")
                        payload = {"user_premium_guild_subscription_slot_ids": [boost_id]}
                        boosted = self.session.put(
                            f"https://discord.com/api/v9/guilds/{self.guild}/premium/subscriptions",
                            json=payload,
                            headers=self.headers,
                        )
                        if boosted.status_code == 201:
                            log("SUCCESS", f"Boosted {self.invite} with {self.token[:23]}***-***")
                            write_to_file("output/boosted.txt", self.full_token)
                        else:
                            log("ERROR", f"Boosting Error: {boosted.text}")
                            write_to_file("output/boosting_error.txt", self.full_token)
                else:
                    log("ERROR", "Failed To Fetch Boost Data")
            except Exception:
                logging.exception("Exception in put_boost")
        else:
            log("WARN", "Failed To Join... So Not Boosting!")


def process_token(token, invite):
    try:
        ins = BTool(token=token, invite=invite)
        if ins.join_guild():
            ins.put_boost()
    except Exception:
        logging.exception("Error processing token")


# --- Routes ---
@app.route("/", methods=["GET"])
def index_route():
    return "Hello — app is running!", 200


@app.route("/health", methods=["GET"])
def health_route():
    return jsonify(status="ok"), 200


@app.route("/hook", methods=["POST"])
def webhook_handler():
    try:
        payload = request.get_json(silent=True)
        if not payload:
            logging.warning("Webhook called without valid JSON payload")
            return jsonify(error="Invalid or missing JSON"), 400

        item = payload.get("item", {})
        quantity = item.get("quantity")
        ip = payload.get("ip")
        idkuwu = payload.get("id")
        user_agent = payload.get("user_agent")
        email = payload.get("email")
        links = item.get("custom_fields", {}).get("server link", "N/A")

        info = (
            f"INVOICE: {idkuwu}\n"
            f"QUANTITY: {quantity}\n"
            f"SERVER: {links}\n"
            f"IP: {ip}\n"
            f"USER_AGENT: {user_agent}\n"
            f"EMAIL: {email}"
        )
        logging.info("Webhook received:\n%s", info)

        invite = links
        if isinstance(invite, str) and "https://discord.gg/" in invite:
            invite = invite.replace("https://discord.gg/", "")

        try:
            num_b = int(quantity) if quantity is not None else 0
        except Exception:
            num_b = 0

        tokens = []
        tokens_path = os.path.join("input", "tokens.txt")
        if os.path.exists(tokens_path):
            with open(tokens_path, "r", encoding="utf-8") as f:
                tokens = [t.strip() for t in f if t.strip()]

        if num_b > 0:
            tokens = tokens[:num_b]

        if tokens:
            threads = min(20, len(tokens))
            executor = ThreadPoolExecutor(max_workers=threads)
            for tok in tokens:
                executor.submit(process_token, tok, invite)

        with open("uwu.txt", "a", encoding="utf-8") as f:
            f.write(info + "\n")

        return Response("The boosts will be done in some seconds.", mimetype="text/plain", status=200)

    except Exception:
        logging.exception("Error in webhook_handler")
        return Response("Invalid JSON", status=400)


# Print registered routes for debug
for rule in app.url_map.iter_rules():
    logging.info("Registered route: %s methods=%s", rule.rule, list(rule.methods))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# --- Webhook route (POST) ---
@app.route("/hook", methods=["POST"])
def webhook_handler():
    try:
        # Use silent=True so it returns None instead of raising on bad content-type
        payload = request.get_json(silent=True)
        if not payload:
            logging.warning("Webhook called without valid JSON payload")
            return jsonify(error="Invalid or missing JSON"), 400

        # Safely extract data with .get to avoid KeyError
        item = payload.get("item", {})
        quantity = item.get("quantity")
        ip = payload.get("ip")
        idkuwu = payload.get("id")
        user_agent = payload.get("user_agent")
        email = payload.get("email")
        links = item.get("custom_fields", {}).get("server link", "N/A")

        # Basic validation examples
        if idkuwu is None:
            return jsonify(error="Missing id"), 400
        if item == {} and quantity is None:
            # either require item or quantity depending on your webhook spec
            return jsonify(error="Missing item/quantity"), 400

        # Example: format the information to be logged
        info = (
            f"INVOICE: {idkuwu}\n"
            f"QUANTITY: {quantity}\n"
            f"SERVER: {links}\n"
            f"IP: {ip}\n"
            f"USER_AGENT: {user_agent}\n"
            f"EMAIL: {email}"
        )

        logging.info("Webhook received:\n%s", info)

        # TODO: do actual processing here (e.g. enqueue work, call other services)
        # If you need to do heavy work, run it in a background thread to return 200 quickly:
        # executor = ThreadPoolExecutor(max_workers=4)
        # executor.submit(do_processing, payload)

        return jsonify(status="received"), 200

    except Exception as e:
        logging.exception("Exception in webhook_handler: %s", e)
        # Return a generic error to the caller; don't expose internals
        return jsonify(error="internal server error"), 500


# --- Optional: list registered routes at import time (good for debugging with Gunicorn) ---
for rule in app.url_map.iter_rules():
    logging.info("Registered route: %s methods=%s", rule.rule, list(rule.methods))

# --- Run locally only ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


        print(info)
        with open('config.yml') as c:
            config = yaml.safe_load(c)


        def encode_to_base64(json_object):
            json_str = json.dumps(json_object)
            json_bytes = json_str.encode("utf-8")
            base64_bytes = base64.b64encode(json_bytes)
            base64_str = base64_bytes.decode("utf-8")
            return base64_str


        def get_cookies() -> dict:
            try:
                response = requests.get("https://discord.com").cookies
                cookies = {
                    "__dcfduid": response.get("__dcfduid"),
                    "__sdcfduid": response.get("__sdcfduid"),
                    "_cfuvid": response.get("_cfuvid"),
                    "__cfruid": response.get("__cfruid"),
                }
                return cookies
            except Exception as e:
                return {}


        def ran_str():
            return "".join(
                random.choice("9830da1a6f376cc753f0fbc28d1ffbbe")
                for _ in range(len("9830da1a6f376cc753f0fbc28d1ffbbe")))


        def get_context_properties(token):
            chrome = "126"  # chrome_version.
            fingerprint_dict = random.choice(fps)
            ja3 = fingerprint_dict["ja3"]
            user_agent = fingerprint_dict["user-agent"]
            x_super_properties = fingerprint_dict["x-super-properties"]
            session = tls_client.Session(
                client_identifier="chrome_" + chrome,
                ja3_string=ja3,
                random_tls_extension_order=True,
            )
            headers = {
                "accept": "*/*",
                "accept-language": "en-US,en;q=0.9",
                "authorization": token,
                "priority": "u=1, i",
                "referer": "https://discord.com/channels",
                "sec-ch-ua":
                f'"Not)A;Brand";v="99", "Microsoft Edge";v="{chrome}", "Chromium";v="{chrome}"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
                "user-agent": user_agent,
                "x-debug-options": "bugReporterEnabled",
                "x-discord-locale": "en-US",
                "x-discord-timezone": "Asia/Katmandu",
                "x-super-properties": x_super_properties,
            }
            params = {
                "inputValue": invite,
                "with_counts": "true",
                "with_expiration": "true",
            }
            response = session.get(
                "https://discord.com/api/v9/invites/wumpus",
                params=params,
                cookies=get_cookies(),
                headers=headers,
            )
            data_to_encode = {
                "location": "Join Guild",
                "location_guild_id": response.json()["guild"]["id"],
                "location_channel_id": response.json()["channel"]["id"],
                "location_channel_type": 5,
            }
            encoded_data = encode_to_base64(data_to_encode)
            return encoded_data


        def get_fingerprint():
            try:
                fingerprint = httpx.get(f"https://discord.com/api/v10/experiments")
                return fingerprint.json()["fingerprint"]
            except Exception as e:
                return get_fingerprint()


        class btool:

            def __init__(self, token):
                self.chrome = "126"  # chrome_version.
                fingerprint_dict = random.choice(fps)
                self.ja3 = fingerprint_dict["ja3"]
                self.user_agent = fingerprint_dict["user-agent"]
                self.x_super_properties = fingerprint_dict["x-super-properties"]
                self.session = tls_client.Session(client_identifier="chrome_" +
                                                  self.chrome,
                                                  random_tls_extension_order=True)
                if config["UseProxy"]:
                    self.session.proxies = {
                        'https': 'http://' + config["Proxy"],
                        'http': 'http://' + config["Proxy"]
                    }
                else:
                    self.session.proxies = None
                self.token = token.split(":")[2] if "@" in token else token
                log("INFO", f"Using [{self.token[:23]}***-***]")
                self.full_token = token
                self.headers = {
                    "accept": "*/*",
                    "accept-language": "en-US,en;q=0.9",
                    "authorization": self.token,
                    "content-type": "application/json",
                    "origin": "https://discord.com",
                    "priority": "u=1, i",
                    "referer": "https://discord.com",
                    "sec-ch-ua":
                    f'"Not)A;Brand";v="99", "Microsoft Edge";v="{self.chrome}", "Chromium";v="{self.chrome}"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-origin",
                    "user-agent": self.user_agent,
                    "x-debug-options": "bugReporterEnabled",
                    "x-discord-locale": "en-US",
                    "x-discord-timezone": "Asia/Katmandu",
                    "x-super-properties": self.x_super_properties,
                }
                self.join_data = {
                    "session_id": ran_str(),
                }

            def join_guild(self) -> bool:
                r = self.session.post(
                    "https://discord.com/api/v9/invites/" + invite,
                    headers=self.headers,
                    json=self.join_data,
                    cookies=get_cookies(),
                )
                if r.status_code == 200:
                    log("DBG", "Joined Guild: {}".format(invite))
                    self.guild = r.json()["guild"]["id"]
                    return True
                else:
                    log("ERR", f"Failed To Join Guild: {r.json()}")
                    return False

            def put_boost(self) -> bool:
                if self.guild:
                    try:

                        boost_dat = self.session.get(
                            f"https://discord.com/api/v9/users/@me/guilds/premium/subscription-slots",
                            headers=self.headers,
                            cookies=get_cookies(),
                        )
                        if boost_dat.status_code == 200:
                            boost_data = boost_dat.json()
                            for boost in boost_data:
                                boost_id = boost["id"]
                                payload = {
                                    "user_premium_guild_subscription_slot_ids":
                                    [boost_id]
                                }
                                boosted = self.session.put(
                                    f"https://discord.com/api/v9/guilds/{self.guild}/premium/subscriptions",
                                    json=payload,
                                    headers=self.headers,
                                )
                                if boosted.status_code == 201:
                                    log(
                                        "SUCCESS",
                                        f"Boosted Server [{invite}] With {self.token[:23]}***-***",
                                    )
                                    write_to_file("output/boosted.txt",
                                                  self.full_token)
                                elif ("Must wait for premium server subscription cooldown to expire"
                                      in boosted.text):
                                    log(
                                        "ERROR",
                                        f"Insufficient Boosts: {self.token[:23]}***-***",
                                    )
                                    write_to_file("output/boosting_error.txt",
                                                  self.full_token)
                                else:
                                    log("ERROR", f"Boosting Error: {boosted.json()}")
                                    write_to_file("output/boosting_error.txt",
                                                  self.full_token)
                        else:
                            write_to_file("output/boosting_error.txt", self.full_token)
                            log("ERROR", "Failed To Fetch Boost Data")
                    except Exception as e:
                        log("ERROR", "ERROR: {}".format(e))
                else:
                    log("WARN", f"Failed To Join... So Not Boosting!")


        def process(token):
            ins = btool(token=token)
            j = ins.join_guild()
            ins.put_boost()

        
        invite = links
        threads = 20
        num_b = quantity
        if "https://discord.gg/" in invite:
            invite = invite.replace("https://discord.gg/", "")
        else:
            invite = invite
        with open("input/tokens.txt", "r") as f:
            tokens = f.read().splitlines()[:num_b]

        with ThreadPoolExecutor(max_workers=threads) as exc:
            for tok in tokens:
                exc.submit(process, tok)

        # Write the information to uwu.txt
        with open("uwu.txt", "a") as f:
            f.write(info)

    except Exception as e:
        # Print the detailed error if something goes wrong
        print(f"Error: {traceback.format_exc()}")
        return Response("Invalid JSON", status=400)

    # Send a response back indicating the process was successful
    deliverables = "The boosts will be done in some seconds."
    return Response(deliverables, mimetype='text/plain', status=200)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=1010)



