from __future__ import annotations

import asyncio
import json
from pprint import pprint
from typing import Optional, Dict

import aiohttp
import click
from blspy import PrivateKey, G1Element, G2Element
from cdv.cmds.util import parse_program
from chia.cmds.cmds_util import CMDTXConfigLoader
from chia.consensus.default_constants import DEFAULT_CONSTANTS
from chia.rpc.wallet_rpc_client import WalletRpcClient
from chia.types.announcement import Announcement
from chia.types.blockchain_format.program import Program
from chia.types.blockchain_format.sized_bytes import bytes32
from chia.types.coin_spend import CoinSpend
from chia.types.condition_opcodes import ConditionOpcode
from chia.types.spend_bundle import SpendBundle
from chia.util.bech32m import encode_puzzle_hash, decode_puzzle_hash
from chia.util.byte_types import hexstr_to_bytes
from chia.util.condition_tools import parse_sexp_to_conditions
from chia.util.config import load_config, selected_network_address_prefix
from chia.util.default_root import DEFAULT_ROOT_PATH
from chia.util.ints import uint16, uint32, uint64
from chia.wallet.puzzles import p2_conditions
from chia.wallet.puzzles.puzzle_utils import make_assert_coin_announcement
from chia.wallet.puzzles.singleton_top_layer_v1_1 import (
    generate_launcher_coin,
    SINGLETON_LAUNCHER,
    SINGLETON_MOD,
    SINGLETON_MOD_HASH,
    SINGLETON_LAUNCHER_HASH,
    solution_for_singleton,
    puzzle_for_singleton,
    lineage_proof_for_coinsol,
)
from chia.wallet.sign_coin_spends import sign_coin_spends
from chia.wallet.transaction_record import TransactionRecord
from chia_rs import Coin
from clvm_tools.binutils import disassemble

from workshop.utils import build

CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])

config = load_config(DEFAULT_ROOT_PATH, "config.yaml")
selected_network = config["wallet"]["selected_network"]
overrides = config["wallet"]["network_overrides"]["constants"][selected_network]
constants = DEFAULT_CONSTANTS.replace_str_to_bytes(**overrides)

fee = uint64(5_000_000 if selected_network == "testnet10" else 0)
tx_config = CMDTXConfigLoader(
    reuse_puzhash=True,
).to_tx_config(1, config, -1)


def monkey_patch_click() -> None:
    # this hacks around what seems to be an incompatibility between the python from `pyinstaller`
    # and `click`
    #
    # Not 100% sure on the details, but it seems that `click` performs a check on start-up
    # that `codecs.lookup(locale.getpreferredencoding()).name != 'ascii'`, and refuses to start
    # if it's not. The python that comes with `pyinstaller` fails this check.
    #
    # This will probably cause problems with the command-line tools that use parameters that
    # are not strict ascii. The real fix is likely with the `pyinstaller` python.

    import click.core

    click.core._verify_python3_env = lambda *args, **kwargs: 0  # type: ignore


@click.group(
    help="\n  Command Line Interface for the Chialisp workshop \n",
    context_settings=CONTEXT_SETTINGS,
)
@click.pass_context
def cli(ctx: click.Context) -> None:
    ctx.ensure_object(dict)


# Loading the client requires the standard chia root directory configuration that all of the chia commands rely on
async def get_wallet_client() -> Optional[WalletRpcClient]:
    try:
        self_hostname = config["self_hostname"]
        wallet_rpc_port = config["wallet"]["rpc_port"]
        wallet_client: Optional[WalletRpcClient] = await WalletRpcClient.create(
            self_hostname, uint16(wallet_rpc_port), DEFAULT_ROOT_PATH, config
        )
        return wallet_client
    except Exception as e:
        if isinstance(e, aiohttp.ClientConnectorError):
            pprint(f"Connection error. Check if wallet is running at {wallet_rpc_port}")
        else:
            pprint(f"Exception from 'harvester' {e}")
        return None


@cli.command("status", short_help="Gets the status of the wallet (get_sync_status)")
def status_cmd():
    async def do_command():
        try:
            wallet_client: WalletRpcClient = await get_wallet_client()
            state: Dict = await wallet_client.fetch("get_sync_status", {})
            height: uint32 = await wallet_client.get_height_info()
            state["height"] = height
            print(json.dumps(state, sort_keys=True, indent=4))
        finally:
            wallet_client.close()
            await wallet_client.await_closed()

    asyncio.get_event_loop().run_until_complete(do_command())


@cli.command("key", short_help="Get my public key")
@click.option("-f", "--fingerprint", help="The wallet fingerprint to use")
def get_public_key_cmd(fingerprint: Optional[str]):
    async def do_command():
        try:
            wallet_client: WalletRpcClient = await get_wallet_client()
            fingerprint_to_use = fingerprint
            if not fingerprint_to_use:
                public_keys = await wallet_client.get_public_keys()
                fingerprint_to_use = public_keys[0]
            private_key: Dict = await wallet_client.get_private_key(fingerprint_to_use)
            print("Public Key: 0x" + private_key.get("pk"))
        finally:
            wallet_client.close()
            await wallet_client.await_closed()

    asyncio.get_event_loop().run_until_complete(do_command())


@cli.command("create-coin", short_help="Creates a coin with a given puzzle file (i.e mypuz.clsp or ./puzzles/*.clsp)")
@click.argument("file", required=True, default=None)
@click.option("-a", "--amount", help="The amount in mojos to send to the new coin", default=1)
def create_coin_cmd(file: str, amount: int):
    async def do_command():
        is_built = build(file)
        if is_built:
            puzzle_hash = parse_program(file + ".hex", "clsp/include").get_tree_hash()
            prefix = selected_network_address_prefix(config)
            address = encode_puzzle_hash(puzzle_hash, prefix)

            click.confirm(
                f"Do you want to send {amount} mojo{'s' if amount > 1 else ''} to your puzzle hash {address})?",
                abort=True,
            )

            try:
                wallet_client: WalletRpcClient = await get_wallet_client()
                transaction: TransactionRecord = await wallet_client.send_transaction(
                    1,
                    uint64(amount),
                    address,
                    CMDTXConfigLoader(
                        reuse_puzhash=True,
                    ).to_tx_config(1, config, -1),
                    fee,
                )
                print(json.dumps(transaction.to_json_dict().get("additions"), sort_keys=True, indent=4))
            finally:
                wallet_client.close()
                await wallet_client.await_closed()

    asyncio.get_event_loop().run_until_complete(do_command())


@cli.command("spend-coin", short_help="Spend coin with a given puzzle file (i.e mypuz.clsp or ./puzzles/*.clsp)")
@click.option("--parentId", required=True, default=None)
@click.option("-a", "--amount", required=True, default=1)
@click.option("--puzzle", required=True, default=None)
@click.option("--solution", required=True, default="()")
def spend_coin_cmd(parentid: str, amount: int, puzzle: str, solution: str):
    async def do_command():
        is_built = True if puzzle.endswith(".hex") else build(puzzle)
        if is_built:
            parsed_puzzle = parse_program(puzzle if puzzle.endswith(".hex") else puzzle + ".hex", "clsp/include")
            parsed_solution = parse_program(solution)

            missing_mojos = 0
            try:
                print("Trying to run the puzzle with this solution...")
                result = parsed_puzzle.run(parsed_solution)
                print("Resulting conditions: " + disassemble(result))

                conditions = parse_sexp_to_conditions(result)
                created_amount = 0
                for condition in conditions:
                    if condition.opcode == ConditionOpcode.CREATE_COIN:
                        created_amount = created_amount + int.from_bytes(condition.vars[1])

                missing_mojos = created_amount - amount
            except Exception as e:
                print("Failed to run puzzle with this solution: " + str(e))
                return

            try:
                wallet_client: WalletRpcClient = await get_wallet_client()

                fingerprint_to_use = None
                if not fingerprint_to_use:
                    public_keys = await wallet_client.get_public_keys()
                    fingerprint_to_use = public_keys[0]
                private_key: Dict = await wallet_client.get_private_key(fingerprint_to_use)

                def pk_to_sk(pk: bytes32) -> Optional[PrivateKey]:
                    if pk == G1Element.from_bytes(bytes.fromhex(private_key.get("pk"))):
                        return PrivateKey.from_bytes(bytes.fromhex(private_key.get("sk")))
                    return None

                coin = Coin(
                    parent_coin_info=hexstr_to_bytes(parentid),
                    amount=amount,
                    puzzle_hash=parsed_puzzle.get_tree_hash(),
                )

                spend_bundle = await sign_coin_spends(
                    [
                        CoinSpend(
                            coin=coin,
                            puzzle_reveal=parsed_puzzle,
                            solution=parsed_solution,
                        )
                    ],
                    pk_to_sk,
                    lambda _: None,
                    constants.AGG_SIG_ME_ADDITIONAL_DATA,
                    constants.MAX_BLOCK_COST_CLVM,
                    [],
                )

                if missing_mojos:
                    print(missing_mojos)
                    # Create an empty coin and immediately spend while checking the auction coin announcement
                    p2_conditions_puzzle = p2_conditions.puzzle_for_conditions(
                        [
                            make_assert_coin_announcement(Announcement(coin.name(), b"$").name()),
                        ]
                    )
                    create_p2_conditions_tx = await wallet_client.create_signed_transaction(
                        [{"amount": missing_mojos, "puzzle_hash": p2_conditions_puzzle.get_tree_hash()}],
                        tx_config,
                        fee=fee,
                    )

                    p2_conditions_spend = CoinSpend(
                        Coin(
                            create_p2_conditions_tx.removals[0].name(),
                            p2_conditions_puzzle.get_tree_hash(),
                            missing_mojos,
                        ),
                        p2_conditions_puzzle,
                        Program.to(0),
                    )
                    spend_bundle = SpendBundle.aggregate(
                        [
                            spend_bundle,
                            create_p2_conditions_tx.spend_bundle,
                            SpendBundle([p2_conditions_spend], G2Element()),
                        ]
                    )

                if fee > 0:
                    my_address = await wallet_client.get_next_address(1, False)
                    my_puzhash = decode_puzzle_hash(my_address)
                    fee_tx = await wallet_client.create_signed_transaction(
                        [{"amount": 0, "puzzle_hash": my_puzhash}],
                        tx_config,
                        fee=fee,
                    )
                    spend_bundle = SpendBundle.aggregate([spend_bundle, fee_tx.spend_bundle])

                print("Spend Bundle:")
                print(json.dumps(spend_bundle.to_json_dict(), sort_keys=True, indent=4))

                print("Pushing transaction...")
                result = await wallet_client.push_tx(spend_bundle)

                print(json.dumps(result, sort_keys=True, indent=4))
            finally:
                wallet_client.close()
                await wallet_client.await_closed()

    asyncio.get_event_loop().run_until_complete(do_command())


@cli.command(
    "create-auction",
    short_help="Creates an auction with a given inner puzzle file (i.e mypuz.clsp or ./clsp/*.clsp)",
)
@click.option("--endHeight", required=True)
def create_auction_cmd(endheight: int):
    async def do_command():
        auction_is_built = build("clsp/5-auction.clsp")
        p2_auction_is_built = build("clsp/5-p2_auction.clsp")
        if auction_is_built and p2_auction_is_built:
            auction_puzzle = parse_program("clsp/5-auction.clsp.hex", "clsp/include")
            p2_auction_puzzle = parse_program("clsp/5-p2_auction.clsp.hex", "clsp/include")
            auction_puzzle_hash = auction_puzzle.get_tree_hash()

            try:
                wallet_client: WalletRpcClient = await get_wallet_client()

                creator_address = await wallet_client.get_next_address(1, False)
                creator_puzhash = decode_puzzle_hash(creator_address)

                curried_auction_puzzle = auction_puzzle.curry(
                    auction_puzzle_hash, creator_puzhash, uint64(endheight), creator_puzhash
                )

                coins = await wallet_client.select_coins(1, 1, tx_config.coin_selection_config)
                origin = coins.copy().pop()

                launcher_coin: Coin = generate_launcher_coin(origin, uint64(1))

                auction_full_puzzle: Program = puzzle_for_singleton(launcher_coin.name(), curried_auction_puzzle)

                launcher_solution = Program.to([auction_full_puzzle.get_tree_hash(), 1, []])
                launcher_coin_spend = CoinSpend(
                    launcher_coin,
                    SINGLETON_LAUNCHER,
                    launcher_solution,
                )

                auction_coin = Coin(launcher_coin.name(), auction_full_puzzle.get_tree_hash(), 1)

                second_bid_amount = 2
                auction_inner_solution = Program.to([0, 1, creator_puzhash, second_bid_amount])
                lineage_proof = lineage_proof_for_coinsol(launcher_coin_spend)
                auction_solution = solution_for_singleton(lineage_proof, auction_coin.amount, auction_inner_solution)
                auction_coin_spend = CoinSpend(
                    auction_coin,
                    auction_full_puzzle,
                    auction_solution,
                )

                result = auction_full_puzzle.run(auction_solution)
                # print(disassemble(result))

                # Create an empty coin and immediately spend while checking the auction coin announcement
                p2_conditions_puzzle = p2_conditions.puzzle_for_conditions(
                    [
                        make_assert_coin_announcement(Announcement(auction_coin.name(), b"$").name()),
                    ]
                )
                p2_conditions_spend = CoinSpend(
                    Coin(origin.name(), p2_conditions_puzzle.get_tree_hash(), second_bid_amount),
                    p2_conditions_puzzle,
                    Program.to(0),
                )

                origin_spend_transaction = await wallet_client.create_signed_transaction(
                    [
                        {"amount": launcher_coin.amount, "puzzle_hash": launcher_coin.puzzle_hash},
                        {"amount": second_bid_amount, "puzzle_hash": p2_conditions_puzzle.get_tree_hash()},
                    ],
                    tx_config,
                    [origin],
                    fee,
                    coin_announcements=[
                        Announcement(launcher_coin.name(), launcher_solution.get_tree_hash()),
                    ],
                )

                spend_bundle = SpendBundle.aggregate(
                    [
                        SpendBundle([launcher_coin_spend, p2_conditions_spend, auction_coin_spend], G2Element()),
                        origin_spend_transaction.spend_bundle,
                    ]
                )

                print("Spend Bundle:")
                print(json.dumps(spend_bundle.to_json_dict(), sort_keys=True, indent=4))

                click.confirm(
                    f"Do you want to create a new auction?",
                    abort=True,
                )

                print("Pushing transaction...")
                result = await wallet_client.push_tx(spend_bundle)

                print(json.dumps(result, sort_keys=True, indent=4))

                expected_auction_inner_puzzle = auction_puzzle.curry(
                    auction_puzzle_hash, creator_puzhash, uint64(endheight), creator_puzhash
                )
                expected_auction_full_puzzle: Program = puzzle_for_singleton(
                    launcher_coin.name(), expected_auction_inner_puzzle
                )

                expected_auction_coin = Coin(
                    auction_coin.name(), expected_auction_full_puzzle.get_tree_hash(), second_bid_amount + 1
                )

                p2_auction_full_puzzle = p2_auction_puzzle.curry(
                    SINGLETON_MOD_HASH, launcher_coin.name(), SINGLETON_LAUNCHER_HASH
                )

                print(f"Auction Launcher ID: `{launcher_coin.name().hex()}`")
                print(f"P2_auction puzzle hash: `{p2_auction_full_puzzle.get_tree_hash().hex()}`")
                print(f"Creator puzzle hash: `{creator_puzhash.hex()}`")
                print(f"End Height: `{endheight}`")
                print(f"Highest bidder puzzle hash: `{creator_puzhash.hex()}`")
                print("")
                print(f"Latest auction coin ID: `{expected_auction_coin.name().hex()}`")
                print(f"Latest auction coin: `{expected_auction_coin.to_json_dict()}`")
                print(f"Latest auction puzzle: `{bytes(expected_auction_full_puzzle).hex()}`")
            finally:
                wallet_client.close()
                await wallet_client.await_closed()

    asyncio.get_event_loop().run_until_complete(do_command())


@cli.command(
    "get-singleton-puzzle",
    short_help="Get a singleton puzzle",
)
@click.argument("file", required=True, default=None)
@click.option("-lid", "--launcherId", help="The launcher ID of the singleton", required=True, default=None)
def get_singleton_puzzle_cmd(file: str, launcherid: str):
    async def do_command():
        is_built = True if file.endswith(".hex") else build(file)
        if is_built:
            parsed_puzzle = parse_program(file if file.endswith(".hex") else file + ".hex", "clsp/include")
            with open(file + ".singleton.hex", "w") as filehandle:
                filehandle.write(
                    bytes(puzzle_for_singleton(bytes.fromhex(launcherid.replace("0x", "")), parsed_puzzle)).hex()
                )

    asyncio.get_event_loop().run_until_complete(do_command())


def main() -> None:
    monkey_patch_click()
    cli()  # pylint: disable=no-value-for-parameter


if __name__ == "__main__":
    main()
