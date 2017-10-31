# Unity Lab [![CircleCI](https://circleci.com/gh/kengz/Unity-Lab.svg?style=shield)](https://circleci.com/gh/kengz/Unity-Lab) [![Maintainability](https://api.codeclimate.com/v1/badges/cd657608713aa907e424/maintainability)](https://codeclimate.com/github/kengz/Unity-Lab/maintainability) [![Test Coverage](https://api.codeclimate.com/v1/badges/cd657608713aa907e424/test_coverage)](https://codeclimate.com/github/kengz/Unity-Lab/test_coverage)
An experimental framework for Reinforcement Learning using Unity and PyTorch.

## Installation

1. Clone the repo:
  ```shell
  git clone https://github.com/kengz/Unity-Lab.git
  ```

2. Install dependencies (or inspect `bin/*` before running):
  ```shell
  bin/setup
  source activate lab
  ```

3. Setup config files:
  -  `config/default.json` for local development, used when `grunt` is ran without a production flag.
  -  `config/production.json` for production lab run when `grunt -prod` is ran with the production flag `-prod`.

## Usage

### Notebook

The Lab uses interactive programming and lit workflow:

1. Install [Atom text editor](https://atom.io/)
2. Install [Hydrogen for Atom](https://atom.io/packages/hydrogen) and [these other Atom packages optionally](https://gist.github.com/kengz/70c20a0cb238ba1fbb29cdfe402c6470#file-packages-json-L3)
3. Use this [killer keymap for Hydrogen and other Atom shortcuts](https://gist.github.com/kengz/70c20a0cb238ba1fbb29cdfe402c6470#file-keymap-cson-L15-L18). Install [Sync Settings](https://atom.io/packages/sync-settings), fork the keymap gist, and update the sync settings config
4. Open and run the example `unity_lab/notebook/hydrogen.py` on Atom using Hydrogen and those keymaps
5. Start working from `unity_lab/notebook/`

### Experiment

_To be set up_

### Unit Test

```shell
yarn test
```
