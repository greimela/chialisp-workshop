Chialisp Workshop Utilities
=======

Prerequisite: Install Chia and switch to Testnet
-------

Download Chia client for your operating system from https://www.chia.net/downloads/

Now find the Chia Command Line Interface for your operating system using the instructions linked here:
https://github.com/Chia-Network/chia-blockchain/wiki/Quick-Start-Guide#using-the-command-line-interface-cli

Switch to testnet by running this command:
```shell
chia configure --testnet true
```

Then start the Chia client and set up your first key.

Install Chialisp workshop utilities
-------

Initialize a new project directory and `cd` into it. Then follow the following instructions to get set up:

```
git clone https://github.com/greimela/chialisp-workshop.git
cd chialisp-workshop
# The following for Linux/MacOS
python3 -m venv venv
. ./venv/bin/activate
# The following for Windows
py -m venv venv
./venv/Scripts/activate
# To install the chialisp-workshop CLI
pip install --extra-index-url https://pypi.chia.net/simple/ .
```

## Check wallet status

```
chiwo status
 ```

## Create a coin

```
chiwo create-coin clsp/1-p2-puzzlehash.clsp
 ```

## Spend a coin

```
 chiwo spend-coin --parentId 0x5978011f08ca96440290a4fddc0cb5bc2bbe559baaf5b8d15f880d41e0d517d4 --puzzle clsp/1-p2-puzzlehash.clsp --solution "(0x33d186b77e34c395103d069ca5979c68cf686113f7fd462fd4fac5b8a4ab6e76 1)"
 ```

## Get the tree hash of a chialisp puzzle

```
cdv clsp treehash -i clsp/include clsp/1-p2-puzzlehash.clsp
```

## Curry parameters into a chialisp puzzle

```
cdv clsp curry -i clsp/include clsp/1-p2-puzzlehash.clsp -a <FIRST_PARAM> -a <SECOND_PARAM> > curried_puzzle.clvm
```