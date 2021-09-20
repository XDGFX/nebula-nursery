#!/usr/bin/env python3

# nebula-nursery.py
#
# A script designed to improve the setup and expansion of Nebula networks. Using
# an interactive config, all the required files can be generated.
#
# Designed to be run on a machine with access to `ca.key` - this should NOT be
# an individual node, but instead a secure separate device (ideally without
# connection to your Nebula network). You can then copy the files to the target node.
#
# XDGFX, 2021
#
# ---
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# ---

import logging
import os
import re
import shutil
import subprocess
from glob import glob
from uuid import uuid4
from zipfile import ZipFile

from cryptography.fernet import Fernet
from flask import Flask, abort, request, send_file
from jinja2 import Template
from PyInquirer import prompt
from pyngrok import ngrok

__version__ = "0.1"

app = Flask(__name__)
os.environ["WERKZEUG_RUN_MAIN"] = "true"
logging.getLogger("werkzeug").setLevel(logging.ERROR)

download_uuid = uuid4()


@app.route("/")
def download_file():
    """
    Serve the output node.zip file to the user.
    """
    code = request.args.get("x")

    if code == str(download_uuid):
        return send_file("node.zip", as_attachment=True)
    else:
        abort(401)


class Nebula:
    def __init__(self) -> None:
        cleanup()

        self.script_dir = os.path.dirname(os.path.realpath(__file__))
        self.executable = self.get_nebula_cert_executable()
        self.lighthouses = []

    def test_executable(self, executable: str) -> bool:
        """
        Run the supplied executable using subprocess, returns True if the command was successful.
        """
        try:
            subprocess.run(
                [executable, "-h"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return "Executable test failed, check you have typed the path correctly."

    def test_ipv4(self, ip: str) -> bool:
        """
        Test if the supplied IP address is a valid IPv4 address.
        """
        return (
            re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", ip) is not None
            or "Invalid IPv4 address"
        )

    def test_ipv4_subnet(self, ip: str) -> bool:
        """
        Test if the supplied IP address is a valid IPv4 address with subnet.
        """
        return (
            re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\/\d{1,2}$", ip) is not None
            or "Invalid IPv4 address. Maybe you are missing the subnet?"
        )

    def get_nebula_cert_executable(self) -> str:
        """
        Prompt the user for the location of the nebula-cert executable.
        """
        nebula_cert = prompt(
            {
                "type": "input",
                "name": "nebula_cert",
                "message": "Please enter the location of the nebula-cert executable.",
                "validate": self.test_executable,
                "default": "nebula-cert",
            }
        ).get("nebula_cert")

        return nebula_cert

    def create_ca(self):
        """
        Prompt the user for name and cert duration, then create a cert using nebula-cert
        """
        ca_name = prompt(
            {
                "type": "input",
                "name": "ca_name",
                "message": "Please enter the name of the new CA.",
                "validate": lambda x: x != "",
            }
        ).get("ca_name")

        ca_duration = prompt(
            {
                "type": "input",
                "name": "ca_duration",
                "message": "Please enter the duration of the CA in days.",
                "default": "3650",
                "validate": lambda x: int(x) > 0,
            }
        ).get("ca_duration")

        # Convert duration to hours
        ca_duration = str(int(ca_duration) * 24) + "h"

        # Ask the user to confirm all input values, if not exit
        if not prompt(
            {
                "type": "confirm",
                "name": "confirm",
                "message": "You entered the following details:\n\n"
                + "CA Name: "
                + ca_name
                + "\nCA Duration: "
                + ca_duration.strip("h")
                + " hours"
                + "\n\nIs this correct?",
            }
        ).get("confirm"):
            raise SystemExit("Please re-run the script and enter new values.")

        # Generate the files
        subprocess.run(
            [
                self.executable,
                "ca",
                "-name",
                ca_name,
                "-duration",
                ca_duration,
                "-out-crt",
                os.path.join(self.script_dir, "ca.crt"),
                "-out-key",
                os.path.join(self.script_dir, "ca.key"),
            ],
            check=True,
        )

        # Compress into a single zip
        with ZipFile("ca.zip", "w") as zip:
            zip.write("ca.crt")
            zip.write("ca.key")

        # Generate a key for encryption
        key = Fernet.generate_key()

        print(
            "The ca encryption key has been generated. Make sure you save this in a safe place!"
        )
        print(f"\n{key.decode()}\n")

        key_validate = (
            prompt(
                {
                    "type": "password",
                    "name": "key_validate",
                    "message": "Please paste the key here to ensure it's copied correctly.",
                    "validate": lambda x: x != "",
                }
            )
            .get("key_validate")
            .encode()
        )

        if key_validate != key:
            raise Exception("The key you entered does not match the key generated.")
        else:
            print("Key validated successfully")

        # Encrypt the zip file
        with open("ca.zip", "rb") as f:
            zip_data = f.read()

        encrypted_zip = Fernet(key).encrypt(zip_data)

        with open("ca.crypt", "wb") as f:
            f.write(encrypted_zip)

        print("Successfully created a ca and stored it securely for future use!")
        print("Re-run this script to generate node keys!")

    def sign_node(self):
        """
        Prompt the user for the node name and ip, and optionally any groups, then sign the node using nebula-cert
        """

        key = (
            prompt(
                {
                    "type": "password",
                    "name": "key_validate",
                    "message": "Please enter the ca encryption key.",
                    "validate": lambda x: x != "",
                }
            )
            .get("key_validate")
            .encode()
        )

        # Extract the encrypted ca files
        with open("ca.crypt", "rb") as f:
            encrypted_zip = f.read()

        zip_data = Fernet(key).decrypt(encrypted_zip)

        with open("ca.zip", "wb") as f:
            f.write(zip_data)

        with ZipFile("ca.zip", "r") as zip:
            zip.extractall()

        # Ask the user to specify if a lighthouse node is to be created
        is_lighthouse = prompt(
            {
                "type": "confirm",
                "name": "is_lighthouse",
                "message": "Is this a lighthouse node?",
                "default": False,
            }
        ).get("is_lighthouse")

        node_name = prompt(
            {
                "type": "input",
                "name": "node_name",
                "message": "Please enter the name of the node.",
                "validate": lambda x: x != "",
            }
        ).get("node_name")

        node_ip = prompt(
            {
                "type": "input",
                "name": "node_ip",
                "message": "Please enter the Nebula IP address to assign to this node. Use IPv4 with subnet notation.",
                "validate": self.test_ipv4_subnet,
            }
        ).get("node_ip")

        node_groups = prompt(
            {
                "type": "input",
                "name": "node_groups",
                "message": "Optionally enter a comma-separated list of groups the node is a member of.",
                "default": "",
            }
        ).get("node_groups")

        # If the node is a lighthouse, prompt for public ip and port
        if is_lighthouse:
            lighthouse_public_ip = prompt(
                {
                    "type": "input",
                    "name": "lighthouse_public_ip",
                    "message": "Please enter the public IP/DNS address of the lighthouse node.",
                    "validate": lambda x: x != "",
                }
            ).get("lighthouse_public_ip")

            lighthouse_port = prompt(
                {
                    "type": "input",
                    "name": "lighthouse_port",
                    "message": "Please enter the local port to listen on. You may need to forward this port through any local firewalls, such as UFW.",
                    "default": "4242",
                    "validate": lambda x: int(x) > 0,
                }
            ).get("lighthouse_port")

            lighthouse_public_port = prompt(
                {
                    "type": "input",
                    "name": "lighthouse_public_port",
                    "message": "Please enter the public port of the lighthouse node. You may need to forward this port through your router.",
                    "default": lighthouse_port,
                    "validate": lambda x: int(x) > 0,
                }
            ).get("lighthouse_public_port")

            # Add the lighthouse to the list of lighthouses
            self.lighthouses.append(
                {
                    "nebula": node_ip,
                    "public": lighthouse_public_ip,
                    "port": lighthouse_public_port,
                }
            )

        add_another_lighthouse = True

        while add_another_lighthouse:
            if len(self.lighthouses) == 0:
                print("You need at least one lighthouse for your node to connect to.")
            else:
                # Ask the user if they want to add another lighthouse
                add_another_lighthouse = prompt(
                    {
                        "type": "confirm",
                        "name": "add_another_lighthouse",
                        "message": "Do you want to add another lighthouse?",
                        "default": False,
                    }
                ).get("add_another_lighthouse")

            if add_another_lighthouse:
                lighthouse_nebula_ip = prompt(
                    {
                        "type": "input",
                        "name": "lighthouse_nebula_ip",
                        "message": "Please enter the Nebula IP of the lighthouse node.",
                        "validate": self.test_ipv4,
                    }
                ).get("lighthouse_nebula_ip")

                lighthouse_public_ip = prompt(
                    {
                        "type": "input",
                        "name": "lighthouse_public_ip",
                        "message": "Please enter the public IP/DNS address of the lighthouse node.",
                        "validate": lambda x: x != "",
                    }
                ).get("lighthouse_public_ip")

                lighthouse_public_port = prompt(
                    {
                        "type": "input",
                        "name": "lighthouse_public_port",
                        "message": "Please enter the public port of the lighthouse node.",
                        "default": "4242",
                        "validate": lambda x: int(x) > 0,
                    }
                ).get("lighthouse_public_port")

                # Add the lighthouse to the list of lighthouses
                self.lighthouses.append(
                    {
                        "nebula": lighthouse_nebula_ip,
                        "public": lighthouse_public_ip,
                        "port": lighthouse_public_port,
                    }
                )

        # Ask the user to confirm all values, if not exit
        prompt_message = (
            "You entered the following details:\n\n"
            + "Node Name: "
            + node_name
            + "\nNebula IP: "
            + node_ip
        )

        if node_groups != "":
            prompt_message += f"\nGroups: {node_groups}"

        prompt_message += "\n\nLighthouses:\n"

        for lighthouse in self.lighthouses:
            lighthouse_message = [
                "",
                f"Lighthouse Nebula IP: {lighthouse['nebula']}\n",
                f"Lighthouse public IP: {lighthouse['public']}\n",
                f"Lighthouse Port: {lighthouse['port']}",
            ]
            prompt_message += "    ".join(lighthouse_message) + "\n\n"

        prompt_message += "Is this correct?"

        if not prompt(
            {
                "type": "confirm",
                "name": "confirm",
                "message": prompt_message,
            }
        ).get("confirm"):
            raise SystemExit("Please re-run the script and enter new values.")

        command = [
            self.executable,
            "sign",
            "-name",
            node_name,
            "-ip",
            node_ip,
            "-out-crt",
            f"{node_name}.crt",
            "-out-key",
            f"{node_name}.key",
        ]

        if node_groups:
            command.extend(["-groups", '"' + node_groups + '"'])

        subprocess.run(
            command,
            check=True,
        )

        with ZipFile("node.zip", "w") as zip:
            zip.write(f"{node_name}.crt")
            zip.write(f"{node_name}.key")
            zip.write("ca.crt")

        # Open an ngrok tunnel to the webserver
        print("\nGenerating a webserver tunnel...")
        http_tunnel = ngrok.connect("8080")

        # Run webserver to allow download of output.zip
        print(
            f"\nFiles successfully generated! They are available at: {http_tunnel.public_url}?x={download_uuid}"
        )
        print("Press Ctrl-C when the files are downloaded to terminate Nebula Nursery.")
        app.run(port=8080)


def cleanup() -> None:
    """
    Remove any files or folders which might exist after execution.
    """

    for file in list(glob("*.crt") + glob("*.key") + glob("*.zip")):
        os.remove(file)


def main():
    """
    Determine if user wants to create a new ca, or to sign a new node.
    """

    splash = f"""
                   _           _
                  | |         | |
        _ __   ___| |__  _   _| | __ _
       | '_ \ / _ \ '_ \| | | | |/ _` |
       | | | |  __/ |_) | |_| | | (_| |
       |_| |_|\___|_.__/ \__,_|_|\__,_|
  _ __  _   _ _ __ ___  ___ _ __ _   _
 | '_ \| | | | '__/ __|/ _ \ '__| | | |
 | | | | |_| | |  \__ \  __/ |  | |_| |
 |_| |_|\__,_|_|  |___/\___|_|   \__, |
                                  __/ |
                           v{__version__}  |___/
    """

    print(splash + "\n")

    nb = Nebula()

    if os.path.exists("ca.crypt"):
        mode = "sign"

        print("\nA certificate authority has already been generated!")

        if not prompt(
            {
                "type": "confirm",
                "name": "confirm",
                "message": "Would you like to sign a new node?",
            }
        ).get("confirm"):
            raise SystemExit(
                "Please remove ca.crypt before signing a new certificate authority."
            )

    else:
        mode = "ca"

    if mode == "ca":
        nb.create_ca()
    elif mode == "sign":
        nb.sign_node()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting...")
        exit(0)
    finally:
        cleanup()
