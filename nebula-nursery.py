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

import os
import subprocess

from jinja2 import Template
from PyInquirer import prompt

# @click.command()
# @click.option(
#     "-n",
#     "--nebula-cert",
#     default="nebula-cert",
#     prompt=True,
#     help="The executable file for nebula-cert. Download from: https://github.com/slackhq/nebula/releases",
# )
# @click.option(
#     "--ca-crt",
#     default="/etc/nebula/ca.crt",
#     prompt=True,
#     help="The location of your ca.crt file",
# )
# @click.option(
#     "--ca-key",
#     default="/etc/nebula/ca.key",
#     prompt=True,
#     help="The location of your ca.key file",
# )
# def get_environment(nebula_cert, ca_crt, ca_key):
#     """
#     Get the environment and check that
#     """
#     click.echo(nebula_cert)
#     click.echo(ca_crt)
#     click.echo(ca_key)

def test_executable(executable: str) -> bool:
    """
    Run the supplied executable using subprocess, returns True if the command was successful.
    """
    try:
        subprocess.run([executable, "-h"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False

def get_nebula_cert_executable() -> str:
    """
    Prompt the user for the location of the nebula-cert executable.
    """
    nebula_cert = prompt({
        "type": "input",
        "name": "nebula_cert",
        "message": "Please enter the location of the nebula-cert executable.",
        "validate": test_executable,
        "default": "nebula-cert"
    }).get("nebula_cert")

    return nebula_cert



def create_ca(nebula_cert):
    """
    Prompt the user for name and cert duration, then create a cert using nebula-cert
    """
    script_dir = os.path.dirname(os.path.realpath(__file__))

    ca_name = prompt({
        "type": "input",
        "name": "ca_name",
        "message": "Please enter the name of the new CA.",
        "validate": lambda x: x != ""
    }).get("ca_name")

    ca_duration = prompt({
        "type": "input",
        "name": "ca_duration",
        "message": "Please enter the duration of the CA in days.",
        "default": "3650",
        "validate": lambda x: int(x) > 0
    }).get("ca_duration")

    # Convert duration to hours
    ca_duration = str(int(ca_duration) * 24) + "h"

    subprocess.run(
        [
            nebula_cert, "ca",
            "-name", ca_name,
            "-duration", ca_duration,
            "-out-crt", os.path.join(script_dir, "output", "ca.crt"),
            "-out-key", os.path.join(script_dir, "output", "ca.key")
        ],
        check=True
    )


def main():
    """
    Determine if user wants to create a new ca, or to sign a new node.
    """
    os.makedirs("output", exist_ok=False)

    mode = prompt({
        "type": "list",
        "name": "mode",
        "message": "Do you want to create a new ca [ca] or sign a new node [sign]?",
        "choices": ["ca", "sign"]
    }).get("mode")

    nebula_cert = get_nebula_cert_executable()

    if mode == "ca":
        create_ca(nebula_cert)


if __name__ == "__main__":
    main()
